#!/bin/sh
# Intent, upload and Apple's processing verdict are different observations.
# This is an always() diagnostic; it must never turn an earlier failure green.
set -eu
if [ "${RELEASE_JOB_STATUS:-}" != "success" ]; then
  if [ "${RELEASE_UPLOAD_OUTCOME:-}" = "success" ]; then
    echo "Release incomplete: upload succeeded, but the workflow did not complete successfully."
    echo "Check Apple's processing verdict and tester access before claiming this build is available."
  else
    echo "Workflow did not complete successfully. No successful upload is established by this run."
  fi
elif [ "${RELEASE_SHIP_INTENT:-}" != "yes" ]; then
  echo "Built and tested only. No upload was requested."
elif [ "${RELEASE_UPLOAD_OUTCOME:-}" = "success" ] && [ "${RELEASE_PROCESSING_OUTCOME:-}" = "success" ]; then
  echo "Build ${ANTICIPY_UPLOAD_BUILD:-unknown} uploaded; Apple's processing check passed."
  echo "Tester access, installation and customer journeys still require verification."
else
  echo "Release incomplete: successful upload and Apple processing are not both established."
fi
