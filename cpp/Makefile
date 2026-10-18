CXX      ?= g++
CXXFLAGS ?= -std=c++20 -O2 -Wall -Wextra -pthread

ticket_sync: main.cpp harness.h coarse_service.h fine_service.h
	$(CXX) $(CXXFLAGS) main.cpp -o $@

clean:
	rm -f ticket_sync

.PHONY: clean
