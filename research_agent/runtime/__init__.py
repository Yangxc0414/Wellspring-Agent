"""Local runtime service for the research agent.

The static Pages site is a showcase. This package exposes a localhost-only
FastAPI service that can execute the real pipeline and read RSI artifacts.
It deliberately has no sign/approve endpoint yet: human gates stay outside
the browser until identity and audit storage are designed.
"""
