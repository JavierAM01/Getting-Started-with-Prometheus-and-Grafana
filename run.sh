#!/usr/bin/bash

source /home/Conda/miniconda3/etc/profile.d/conda.sh
conda activate /home/Conda/p38

python /home/Prometheus/temperaturas/temperaturas.py \
                --config.file=/home/Prometheus/temperaturas/temperaturas.yml \
                --storage.log.path=/home/Prometheus/temperaturas/storage/logger \
                --storage.counter.path=/home/Prometheus/temperaturas/storage/counter

