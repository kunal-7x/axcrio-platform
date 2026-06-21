#!/bin/bash
cd /opt/famit-agent || exit 1
rm -rf /tmp/r6btest && mkdir -p /tmp/r6btest
cp _prompt_r6b_test.py /tmp/r6btest/prompt.py
cp _probe_r6b.py /tmp/r6btest/_probe.py
cd /tmp/r6btest
PYTHONPATH=/opt/famit-agent python3 -c "import py_compile; py_compile.compile('prompt.py', doraise=True); print('COMPILE_OK')"
PYTHONPATH=/opt/famit-agent:/tmp/r6btest python3 _probe.py
