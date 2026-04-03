#! /bin/bash

until gdbus introspect --session --dest org.gnome.Shell --object-path /org/gnome/Shell &> /dev/null; do
    sleep 0.5
done

gnome-terminal &
google-chrome --new-window http://49.234.204.236 https://www.doubao.com github.com/xuchang193 &
clash-verge &
code &
wechat &

echo "autostart.sh done"
exit 0

