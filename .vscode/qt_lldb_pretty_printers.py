# Qt LLDB 完整格式化脚本 (兼容 GCC + Qt5/Qt6 + CodeLLDB)
# 支持：QString, QByteArray, QChar, QList, QVector, QMap, QHash, QSet, QVariant,
#      QPoint/QPointF, QSize/QSizeF, QRect/QRectF, QLine/QLineF, QMargins,
#      QDate, QTime, QColor
import lldb
import sys

MAX_STRING_BYTES = 4096

QMETATYPE_NAMES = {
    0: "Invalid",
    1: "bool",
    2: "int",
    3: "uint",
    4: "qlonglong",
    5: "qulonglong",
    6: "double",
    7: "QChar",
    8: "QVariantMap",
    9: "QVariantList",
    10: "QString",
    11: "QStringList",
    12: "QByteArray",
    13: "QBitArray",
    14: "QDate",
    15: "QTime",
    16: "QDateTime",
    17: "QUrl",
    18: "QLocale",
    19: "QRect",
    20: "QRectF",
    21: "QSize",
    22: "QSizeF",
    23: "QLine",
    24: "QLineF",
    25: "QPoint",
    26: "QPointF",
    27: "QRegExp",
    28: "QVariantHash",
    29: "QEasingCurve",
    30: "QUuid",
    32: "long",
    33: "short",
    34: "char",
    35: "ulong",
    36: "ushort",
    37: "uchar",
    38: "float",
    39: "QObject*",
    41: "QVariant",
    44: "QRegularExpression",
    45: "QJsonValue",
    46: "QJsonObject",
    47: "QJsonArray",
    48: "QJsonDocument",
    49: "QByteArrayList",
    64: "QFont",
    65: "QPixmap",
    66: "QBrush",
    67: "QColor",
    68: "QPalette",
    69: "QIcon",
    70: "QImage",
    75: "QKeySequence",
    76: "QPen",
    80: "QTransform",
    81: "QMatrix4x4",
    82: "QVector2D",
    83: "QVector3D",
    84: "QVector4D",
    85: "QQuaternion",
}


def _member(value, name):
    child = value.GetChildMemberWithName(name)
    return child if child.IsValid() else None


def _pointee(value):
    if not value or not value.IsValid():
        return None
    try:
        if value.GetType().IsPointerType():
            pointee = value.Dereference()
            return pointee if pointee.IsValid() else None
    except:
        pass
    return value


def _integer(value, signed=False, default=None):
    if not value or not value.IsValid():
        return default
    try:
        if signed:
            return value.GetValueAsSigned(default if default is not None else 0)
        return value.GetValueAsUnsigned(default if default is not None else 0)
    except:
        return default


def _float(value, default=None):
    if not value or not value.IsValid():
        return default
    try:
        return float(value.GetValue())
    except:
        return default


def _address_of(value):
    if not value or not value.IsValid():
        return None
    try:
        address = value.AddressOf()
        if address.IsValid():
            return address.GetValueAsUnsigned(0)
    except:
        pass
    try:
        return value.GetLoadAddress()
    except:
        return None


def _type_value_at(value, type_name, address):
    if not address:
        return None
    try:
        target = value.GetTarget()
        value_type = target.FindFirstType(type_name)
        if not value_type.IsValid():
            return None
        typed_value = value.CreateValueFromAddress(type_name, address, value_type)
        return typed_value if typed_value.IsValid() else None
    except:
        return None


def _qarray_data(value):
    d = _member(value, "d")
    if not d:
        return None

    try:
        # Qt 6 stores QString/QByteArray data in QArrayDataPointer:
        # { d: header pointer, ptr: character pointer, size: element count }.
        if not d.GetType().IsPointerType():
            ptr = _member(d, "ptr")
            size = _integer(_member(d, "size"), signed=True)
            addr = _integer(ptr)
            if size is not None and size >= 0 and addr:
                return addr, size
    except:
        pass

    data_header = _pointee(d)
    if not data_header:
        return None

    # Qt 5 stores d as a QArrayData/QTypedArrayData pointer. The character data
    # starts at d + d->offset; d's type size is only the pointer size.
    size = _integer(_member(data_header, "size"), signed=True)
    offset = _integer(_member(data_header, "offset"), signed=True)
    base_addr = _integer(d)
    if size is None or offset is None or not base_addr:
        return None
    if size < 0:
        return None

    return base_addr + offset, size


def _container_size_from_d_pointer(value):
    d = _member(value, "d")
    header = _pointee(d)
    size = _integer(_member(header, "size"), signed=True)
    if size is not None:
        return size
    return None


def _qlist_size(value):
    try:
        d = _pointee(_member(value, "d"))
        begin = _integer(_member(d, "begin"), signed=True)
        end = _integer(_member(d, "end"), signed=True)
        if begin is not None and end is not None:
            return end - begin
    except:
        pass
    try:
        p = _member(value, "p")
        d = _pointee(_member(p, "d"))
        begin = _integer(_member(d, "begin"), signed=True)
        end = _integer(_member(d, "end"), signed=True)
        if begin is not None and end is not None:
            return end - begin
    except:
        pass
    try:
        for index in range(value.GetNumChildren()):
            child = value.GetChildAtIndex(index)
            if child.IsValid() and child.GetTypeName().startswith("QList<"):
                return _qlist_size(child)
    except:
        pass
    return None


def _quote_summary(text, truncated=False):
    escaped = (
        text.replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\n", "\\n")
            .replace("\r", "\\r")
            .replace("\t", "\\t")
    )
    if truncated:
        escaped += "..."
    return f'"{escaped}"'


def _format_float(value):
    return f"{value:.12g}"


def _int_pair_summary(value, first, second, name):
    a = _integer(_member(value, first), signed=True)
    b = _integer(_member(value, second), signed=True)
    if a is None or b is None:
        return f"<{name}>"
    return f"{name}({a}, {b})"


def _float_pair_summary(value, first, second, name):
    a = _float(_member(value, first))
    b = _float(_member(value, second))
    if a is None or b is None:
        return f"<{name}>"
    return f"{name}({_format_float(a)}, {_format_float(b)})"


def _qdate_text_from_julian_day(jd):
    if jd == -(1 << 63):
        return "QDate(null)"
    if jd < -784350574879 or jd > 784354017364:
        return f"QDate(invalid, jd={jd})"

    # Fliegel-Van Flandern conversion from Julian day number to Gregorian date.
    l = jd + 68569
    n = (4 * l) // 146097
    l = l - (146097 * n + 3) // 4
    i = (4000 * (l + 1)) // 1461001
    l = l - (1461 * i) // 4 + 31
    j = (80 * l) // 2447
    day = l - (2447 * j) // 80
    l = j // 11
    month = j + 2 - 12 * l
    year = 100 * (n - 49) + i + l
    return f"QDate({year:04d}-{month:02d}-{day:02d})"


def _qtime_text_from_msecs(msecs):
    if msecs == -1:
        return "QTime(null)"
    if msecs < 0 or msecs >= 24 * 60 * 60 * 1000:
        return f"QTime(invalid, msecs={msecs})"
    hours = msecs // (60 * 60 * 1000)
    msecs %= 60 * 60 * 1000
    minutes = msecs // (60 * 1000)
    msecs %= 60 * 1000
    seconds = msecs // 1000
    msecs %= 1000
    return f"QTime({hours:02d}:{minutes:02d}:{seconds:02d}.{msecs:03d})"

# ====================== QString 格式化 ======================
def qstring_summary(valobj, internal_dict):
    try:
        data = _qarray_data(valobj)
        if not data:
            return "<QString>"

        addr, size = data
        if size == 0:
            return '""'

        byte_count = size * 2
        truncated = byte_count > MAX_STRING_BYTES
        byte_count = min(byte_count, MAX_STRING_BYTES)
        error = lldb.SBError()
        str_data = valobj.GetProcess().ReadMemory(addr, byte_count, error)
        if error.Success():
            encoding = "utf-16le" if sys.byteorder == "little" else "utf-16be"
            return _quote_summary(str_data.decode(encoding, errors="replace"), truncated)
    except:
        pass
    return "<QString>"

# ====================== QByteArray 格式化 ======================
def qbytearray_summary(valobj, internal_dict):
    try:
        data = _qarray_data(valobj)
        if not data:
            return "<QByteArray>"

        addr, size = data
        if size == 0:
            return '""'

        byte_count = min(size, MAX_STRING_BYTES)
        truncated = size > MAX_STRING_BYTES
        error = lldb.SBError()
        raw = valobj.GetProcess().ReadMemory(addr, byte_count, error)
        if error.Success():
            return _quote_summary(raw.decode("utf-8", errors="replace"), truncated)
    except:
        pass
    return "<QByteArray>"


# ====================== QChar 格式化 ======================
def qchar_summary(valobj, internal_dict):
    try:
        code = _integer(_member(valobj, "ucs"))
        if code is None:
            return "<QChar>"
        text = chr(code)
        if code < 0x20 or 0xD800 <= code <= 0xDFFF:
            return f"QChar(U+{code:04X})"
        return f"QChar('{text}', U+{code:04X})"
    except:
        return "<QChar>"


# ====================== QList / QVector 格式化 ======================
def qlist_summary(valobj, internal_dict):
    try:
        size = _qlist_size(valobj)
        if size is not None:
            return f"size={size}"
    except:
        pass
    return "<QList>"


def qvector_summary(valobj, internal_dict):
    try:
        size = _container_size_from_d_pointer(valobj)
        if size is not None:
            return f"size={size}"
    except:
        pass
    return "<QVector>"

# ====================== QMap / QHash 格式化 ======================
def qmap_summary(valobj, internal_dict):
    try:
        size = _container_size_from_d_pointer(valobj)
        if size is not None:
            return f"size={size}"
    except:
        pass
    return "<QMap/QHash>"


def qset_summary(valobj, internal_dict):
    try:
        q_hash = _member(valobj, "q_hash")
        size = _container_size_from_d_pointer(q_hash)
        if size is not None:
            return f"size={size}"
    except:
        pass
    return "<QSet>"


# ====================== 常用值类型格式化 ======================
def qpoint_summary(valobj, internal_dict):
    return _int_pair_summary(valobj, "xp", "yp", "QPoint")


def qpointf_summary(valobj, internal_dict):
    return _float_pair_summary(valobj, "xp", "yp", "QPointF")


def qsize_summary(valobj, internal_dict):
    return _int_pair_summary(valobj, "wd", "ht", "QSize")


def qsizef_summary(valobj, internal_dict):
    return _float_pair_summary(valobj, "wd", "ht", "QSizeF")


def qrect_summary(valobj, internal_dict):
    try:
        x1 = _integer(_member(valobj, "x1"), signed=True)
        y1 = _integer(_member(valobj, "y1"), signed=True)
        x2 = _integer(_member(valobj, "x2"), signed=True)
        y2 = _integer(_member(valobj, "y2"), signed=True)
        if None in (x1, y1, x2, y2):
            return "<QRect>"
        return f"QRect({x1}, {y1}, {x2 - x1 + 1}, {y2 - y1 + 1})"
    except:
        return "<QRect>"


def qrectf_summary(valobj, internal_dict):
    try:
        x = _float(_member(valobj, "xp"))
        y = _float(_member(valobj, "yp"))
        w = _float(_member(valobj, "w"))
        h = _float(_member(valobj, "h"))
        if None in (x, y, w, h):
            return "<QRectF>"
        return (
            f"QRectF({_format_float(x)}, {_format_float(y)}, "
            f"{_format_float(w)}, {_format_float(h)})"
        )
    except:
        return "<QRectF>"


def qline_summary(valobj, internal_dict):
    try:
        pt1 = _member(valobj, "pt1")
        pt2 = _member(valobj, "pt2")
        x1 = _integer(_member(pt1, "xp"), signed=True)
        y1 = _integer(_member(pt1, "yp"), signed=True)
        x2 = _integer(_member(pt2, "xp"), signed=True)
        y2 = _integer(_member(pt2, "yp"), signed=True)
        if None in (x1, y1, x2, y2):
            return "<QLine>"
        return f"QLine(({x1}, {y1}) -> ({x2}, {y2}))"
    except:
        return "<QLine>"


def qlinef_summary(valobj, internal_dict):
    try:
        pt1 = _member(valobj, "pt1")
        pt2 = _member(valobj, "pt2")
        x1 = _float(_member(pt1, "xp"))
        y1 = _float(_member(pt1, "yp"))
        x2 = _float(_member(pt2, "xp"))
        y2 = _float(_member(pt2, "yp"))
        if None in (x1, y1, x2, y2):
            return "<QLineF>"
        return (
            f"QLineF(({_format_float(x1)}, {_format_float(y1)}) -> "
            f"({_format_float(x2)}, {_format_float(y2)}))"
        )
    except:
        return "<QLineF>"


def qmargins_summary(valobj, internal_dict):
    try:
        left = _integer(_member(valobj, "m_left"), signed=True)
        top = _integer(_member(valobj, "m_top"), signed=True)
        right = _integer(_member(valobj, "m_right"), signed=True)
        bottom = _integer(_member(valobj, "m_bottom"), signed=True)
        if None in (left, top, right, bottom):
            return "<QMargins>"
        return f"QMargins({left}, {top}, {right}, {bottom})"
    except:
        return "<QMargins>"


def qdate_summary(valobj, internal_dict):
    try:
        jd = _integer(_member(valobj, "jd"), signed=True)
        if jd is None:
            return "<QDate>"
        return _qdate_text_from_julian_day(jd)
    except:
        return "<QDate>"


def qtime_summary(valobj, internal_dict):
    try:
        msecs = _integer(_member(valobj, "mds"), signed=True)
        if msecs is None:
            return "<QTime>"
        return _qtime_text_from_msecs(msecs)
    except:
        return "<QTime>"


def qcolor_summary(valobj, internal_dict):
    try:
        spec = _integer(_member(valobj, "cspec"))
        if spec == 0:
            return "QColor(invalid)"

        ct = _member(valobj, "ct")
        spec_names = {
            1: "Rgb",
            2: "Hsv",
            3: "Cmyk",
            4: "Hsl",
            5: "ExtendedRgb",
        }
        if spec == 1:
            argb = _member(ct, "argb")
            alpha = _integer(_member(argb, "alpha")) // 257
            red = _integer(_member(argb, "red")) // 257
            green = _integer(_member(argb, "green")) // 257
            blue = _integer(_member(argb, "blue")) // 257
            return f"QColor(r={red}, g={green}, b={blue}, a={alpha})"

        array = _member(ct, "array")
        values = []
        for index in range(5):
            child = array.GetChildAtIndex(index)
            values.append(_integer(child))
        return f"QColor({spec_names.get(spec, spec)}, raw={values})"
    except:
        return "<QColor>"


def _qvariant_type_name(type_id):
    if type_id >= 1024:
        return f"UserType({type_id})"
    return QMETATYPE_NAMES.get(type_id, f"type {type_id}")


def _qvariant_payload_address(valobj, private_value):
    data = _member(private_value, "data")
    is_shared = _integer(_member(private_value, "is_shared"))
    if is_shared:
        shared = _pointee(_member(data, "shared"))
        return _integer(_member(shared, "ptr"))
    return _address_of(_member(data, "ptr"))


def _qvariant_payload_summary(valobj, private_value, type_id):
    data = _member(private_value, "data")
    try:
        if type_id == 1:
            return "true" if _integer(_member(data, "b")) else "false"
        if type_id == 2:
            return str(_integer(_member(data, "i"), signed=True))
        if type_id == 3:
            return str(_integer(_member(data, "u")))
        if type_id == 4:
            return str(_integer(_member(data, "ll"), signed=True))
        if type_id == 5:
            return str(_integer(_member(data, "ull")))
        if type_id == 6:
            return _format_float(_float(_member(data, "d")))
        if type_id == 38:
            return _format_float(_float(_member(data, "f")))
    except:
        return None

    address = _qvariant_payload_address(valobj, private_value)
    type_handlers = {
        7: ("QChar", qchar_summary),
        10: ("QString", qstring_summary),
        12: ("QByteArray", qbytearray_summary),
        14: ("QDate", qdate_summary),
        15: ("QTime", qtime_summary),
        19: ("QRect", qrect_summary),
        20: ("QRectF", qrectf_summary),
        21: ("QSize", qsize_summary),
        22: ("QSizeF", qsizef_summary),
        23: ("QLine", qline_summary),
        24: ("QLineF", qlinef_summary),
        25: ("QPoint", qpoint_summary),
        26: ("QPointF", qpointf_summary),
        67: ("QColor", qcolor_summary),
    }
    handler = type_handlers.get(type_id)
    if not handler:
        return None

    type_name, summary = handler
    payload = _type_value_at(valobj, type_name, address)
    if not payload:
        return None
    return summary(payload, {})


def qvariant_summary(valobj, internal_dict):
    try:
        private_value = _member(valobj, "d")
        type_id = _integer(_member(private_value, "type"))
        if type_id is None or type_id == 0:
            return "QVariant(invalid)"

        type_name = _qvariant_type_name(type_id)
        is_null = _integer(_member(private_value, "is_null"))
        payload = _qvariant_payload_summary(valobj, private_value, type_id)
        null_text = ", null" if is_null else ""
        if payload:
            return f"QVariant({type_name}, {payload}{null_text})"
        return f"QVariant({type_name}{null_text})"
    except:
        return "<QVariant>"

# ====================== 注册所有类型 ======================
def __lldb_init_module(debugger, internal_dict):
    # 核心字符串
    debugger.HandleCommand('type summary add QString -F qt_lldb_pretty_printers.qstring_summary')
    debugger.HandleCommand('type summary add QByteArray -F qt_lldb_pretty_printers.qbytearray_summary')
    debugger.HandleCommand('type summary add QChar -F qt_lldb_pretty_printers.qchar_summary')
    
    # 容器只做轻量 size 摘要；元素展开需要 synthetic children，单独实现更合适。
    debugger.HandleCommand('type summary add QStringList -F qt_lldb_pretty_printers.qlist_summary')
    debugger.HandleCommand('type summary add -x "^QList<.+>$" -F qt_lldb_pretty_printers.qlist_summary')
    debugger.HandleCommand('type summary add -x "^QVector<.+>$" -F qt_lldb_pretty_printers.qvector_summary')
    debugger.HandleCommand('type summary add -x "^QMap<.+>$" -F qt_lldb_pretty_printers.qmap_summary')
    debugger.HandleCommand('type summary add -x "^QMultiMap<.+>$" -F qt_lldb_pretty_printers.qmap_summary')
    debugger.HandleCommand('type summary add -x "^QHash<.+>$" -F qt_lldb_pretty_printers.qmap_summary')
    debugger.HandleCommand('type summary add -x "^QMultiHash<.+>$" -F qt_lldb_pretty_printers.qmap_summary')
    debugger.HandleCommand('type summary add -x "^QSet<.+>$" -F qt_lldb_pretty_printers.qset_summary')

    # 常用 Core/Gui 值类型
    debugger.HandleCommand('type summary add QPoint -F qt_lldb_pretty_printers.qpoint_summary')
    debugger.HandleCommand('type summary add QPointF -F qt_lldb_pretty_printers.qpointf_summary')
    debugger.HandleCommand('type summary add QSize -F qt_lldb_pretty_printers.qsize_summary')
    debugger.HandleCommand('type summary add QSizeF -F qt_lldb_pretty_printers.qsizef_summary')
    debugger.HandleCommand('type summary add QRect -F qt_lldb_pretty_printers.qrect_summary')
    debugger.HandleCommand('type summary add QRectF -F qt_lldb_pretty_printers.qrectf_summary')
    debugger.HandleCommand('type summary add QLine -F qt_lldb_pretty_printers.qline_summary')
    debugger.HandleCommand('type summary add QLineF -F qt_lldb_pretty_printers.qlinef_summary')
    debugger.HandleCommand('type summary add QMargins -F qt_lldb_pretty_printers.qmargins_summary')
    debugger.HandleCommand('type summary add QDate -F qt_lldb_pretty_printers.qdate_summary')
    debugger.HandleCommand('type summary add QTime -F qt_lldb_pretty_printers.qtime_summary')
    debugger.HandleCommand('type summary add QColor -F qt_lldb_pretty_printers.qcolor_summary')
    debugger.HandleCommand('type summary add QVariant -F qt_lldb_pretty_printers.qvariant_summary')

    print("✅ Qt 格式化加载完成：QString | QByteArray | QChar | containers | value types | QVariant")
