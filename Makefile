SHELL := /bin/bash

.PHONY: all build release debug clean

all: build

build: release
	@echo "Build complete (release)"

release:
	swift build -c release
	mkdir -p bin
	cp -f .build/release/aligner bin/slog-aligner
	chmod +x bin/slog-aligner
	@echo "Built release aligner into bin/slog-aligner"

debug:
	swift build -c debug
	mkdir -p bin
	cp -f .build/debug/aligner bin/slog-aligner
	chmod +x bin/slog-aligner
	@echo "Built debug aligner into bin/slog-aligner"

clean:
	rm -f bin/slog-aligner
	swift package clean
	@echo "Cleaned"


