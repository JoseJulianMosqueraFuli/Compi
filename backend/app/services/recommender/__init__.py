"""Recommender: pure functions that organize the week and prescribe the training.

- availability / scheduler: when each session happens, given the free windows.
- catalog / training: what each session contains, given the history.
- duration / shorten: how long it takes and how to make it fit a smaller window.
- compare: recommended versus performed.
"""
