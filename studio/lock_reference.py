"""Fige (volontairement) l'état actuel des références visuelles et vocales : python -m studio.lock_reference"""
from studio.narrative.memory import MEM, reference_fingerprint

(MEM / "reference.lock").write_text(reference_fingerprint() + "\n")
print("Références figées :", (MEM / "reference.lock").read_text().strip())
