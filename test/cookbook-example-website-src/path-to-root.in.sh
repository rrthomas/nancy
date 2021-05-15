#!/bin/sh
# Output the path from the first argument to the root of the directory
echo "$1" | sed s:[^./][^/]*:\.\.:g
