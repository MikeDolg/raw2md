"""Shared markdown text primitives: protected zones and structural detectors.

The cleaner, the quality evaluator, the LLM edit guard, and post-processing
read the same protected zones (front matter, fenced code, HTML tables) and the
same detectors (tables, images, formulas, repetition loops). One definition
keeps their verdicts on one body in agreement. The package depends on no
cleaning policy, verdict, or LLM operation.

The package classifies and detects. The few functions that write text live
beside their detector so that the two cannot drift: the lost-page marker, the
page mark, and the repetition-loop trim.
"""
