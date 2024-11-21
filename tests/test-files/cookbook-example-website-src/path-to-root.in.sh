#!/bin/sh
# Output the path from the first argument to the root of the directory
echo "$(dirname \\"$1\\")" | sed 's:[^. /][^/]*:\.\.:g'
