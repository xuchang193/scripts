#! /bin/bash
ps -aux | grep username | grep code | awk '{print $2}' | xargs kill -9
exit 0
