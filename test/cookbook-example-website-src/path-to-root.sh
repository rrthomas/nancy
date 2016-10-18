#!/bin/sh
# Output the path from the first argument to the root of the directory
dirname "$1" | sed s:[^./][^/]*:\.\.:g
