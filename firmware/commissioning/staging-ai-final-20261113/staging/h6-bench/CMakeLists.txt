# SPDX-License-Identifier: Apache-2.0
# ColdGuard H6 - isolated TEC polarity bench-test firmware.
# This project is deliberately separate from firmware/ (production W04).
cmake_minimum_required(VERSION 3.16)

include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(coldguard_h6_bench)
