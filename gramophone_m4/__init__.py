"""Gramophone M4: adaptive play (next-beat-driven sessions).

Pure policy over reused engines: each pick computes mastered -> fringe ->
next_beat, binds the picked beat's checks to the response stream (pulling
retry responses on fails), and grades through the M3 engine with restore
chaining. No duplicated learning logic.
"""

__version__ = "0.4.0"
