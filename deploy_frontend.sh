#!/usr/bin/env bash
# Change this path to your deployment location.
cd /home/theo/PycharmProjects/thems_facts/front_end_service || exit
gcloud app deploy ./front_end_app.yaml --quiet
gcloud app browse
