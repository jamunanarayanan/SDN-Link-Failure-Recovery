#!/bin/bash
python3 test_m3.py > /dev/null && python3 evaluate_models.py && echo "all offline checks finished"
