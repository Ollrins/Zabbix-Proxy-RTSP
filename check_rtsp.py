#!/bin/bash
SCRIPT="/usr/lib/zabbix/externalscripts/check_rtsp_impl.py"
ERRLOG="/var/log/check_rtsp_wrapper.err"
MAX_MB=15

if [ -f "$ERRLOG" ]; then
    SIZE=$(du -m "$ERRLOG" 2>/dev/null | cut -f1)
    if [ "${SIZE:-0}" -gt "$MAX_MB" ]; then
        > "$ERRLOG"
    fi
fi

if [ ! -x "$SCRIPT" ]; then
    echo "{\"status\":\"error\",\"note\":\"impl script not found: $SCRIPT\"}"
    exit 1
fi

"$SCRIPT" "$@" 2>>"$ERRLOG" | sed -n '/^{/,$p'
exit ${PIPESTATUS[0]}
