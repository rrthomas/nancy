#!/bin/sh
# Output the path from the first argument to the root of the directory
printf "%s" "$(dirname \\"$1\\")" | sed 's:[^. /][^/]*:\.\.:g'
