#!/bin/bash

set -e -x

python3 -m venv venv3
venv3/bin/pip install -r requirements.txt
test -d sawtooth-core || git clone https://github.com/hyperledger/sawtooth-core
(cd sawtooth-core && ./bin/protogen)
venv3/bin/pip install -e ./sawtooth-core/signing
venv3/bin/pip install -e ./sawtooth-core/sdk/python
test -d omi-summer-lab || git clone https://github.com/IntelLedger/omi-summer-lab
(cd omi-summer-lab && ./bin/protogen)
