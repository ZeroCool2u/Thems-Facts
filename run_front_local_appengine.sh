#!/usr/bin/env bash
deactivate || exit
cd /home/theo/PycharmProjects/thems_facts/front_end_service/ || exit
dev_appserver.py --application=facts-sender front_end_app.yaml
