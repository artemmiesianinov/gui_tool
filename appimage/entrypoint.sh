#! /bin/bash
# Run the bundled interpreter directly rather than through python-appimage's usr/bin/python3.x wrapper. That wrapper
# doesn't exec, so every Python process would get an extra bash parent, and child processes that check os.getppid()
# (e.g. the MAVCAN and SLCAN driver I/O processes) would think the application has died and quit. Leaving
# APPIMAGE_COMMAND unset also keeps sys.executable pointing at this interpreter, so multiprocessing starts its children
# with it directly instead of relaunching the whole AppImage.
PYTHON="${APPDIR}/opt/python{{ python-version }}/bin/python{{ python-version }}"
unset APPIMAGE_COMMAND
export SSL_CERT_FILE="${APPDIR}/opt/_internal/certs.pem"

# Called with Python options (e.g. "-I -c ..."): behave as the Python interpreter. The app's own options are long
# ones, apart from -h.
case "$1" in
    -h) ;;
    -[!-]*) exec "$PYTHON" "$@" ;;
esac

# -I keeps the bundled Python isolated from the user's site-packages and PYTHONPATH
exec "$PYTHON" -I "${APPDIR}/opt/python{{ python-version }}/bin/dronecan_gui_tool" "$@"
