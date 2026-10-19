#!/bin/bash
# Starts countess_web in a batch job. The address to open (which holds the private access token)
# and the SSH tunnel to reach it are written to ~/.countess-web/job-<jobid>.txt, readable only by
# you; the job's output file (countess_web-<jobid>.out) says where. The server stops when the
# job's time runs out or it is cancelled (scancel <jobid>).
#
# Usage: sbatch countess_web.sbatch [pipeline.ini]
#
# Adjust the resources, and add whatever your site needs (partition, account, modules, the
# Python environment holding countess-web).

#SBATCH --job-name=countess_web
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=08:00:00
#SBATCH --output=countess_web-%j.out

set -euo pipefail

exec countess_web --no-browser "$@"
