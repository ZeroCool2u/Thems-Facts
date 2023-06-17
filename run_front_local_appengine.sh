#!/usr/bin/env bash
cd /home/theo/PycharmProjects/thems_facts/front_end_service/ || exit
python3 /usr/lib/google-cloud-sdk/bin/dev_appserver.py front_end_app.yaml
