"""Tileable fractal-noise cloud sheet for the landing atmosphere layer.

Built in the frequency domain: a spectrum shaped by 1/f over a discrete FFT
grid is periodic by construction, so the sheet repeats without a seam. A
spatial-domain blur would not tile and shows as vertical banding on the page.
"""
import numpy as np
from PIL import Image

N = 1024
rng = np.random.default_rng(20260908)

fy = np.fft.fftfreq(N)[:, None]
fx = np.fft.fftfreq(N)[None, :]
# clouds stretch along the wind, so the spectrum is anisotropic
radius = np.hypot(fy, fx * 1.9)
radius[0, 0] = 1.0

# 1/f^beta falloff gives cloud-like structure; the band limit removes the
# pixel-scale fizz that would otherwise read as noise rather than vapour.
spectrum = radius ** -1.95
spectrum[radius > 0.5] = 0.0
spectrum[0, 0] = 0.0

phase = rng.uniform(0, 2 * np.pi, (N, N))
field = np.real(np.fft.ifft2(spectrum * np.exp(1j * phase)))
field = (field - field.mean()) / field.std()

# threshold into banks of cloud with clear sky between them
alpha = np.clip((field + 0.35) / 2.1, 0, 1) ** 1.5
alpha = (alpha * 245).astype(np.uint8)

white = np.full((N, N, 3), 244, np.uint8)
Image.fromarray(np.dstack([white, alpha])).save("public/geo/clouds.png", optimize=True)

# seam check: opposite edges must agree because the field is periodic
seam = np.abs(alpha[0].astype(int) - alpha[-1].astype(int)).mean()
print(f"clouds.png mean alpha {alpha.mean():.1f}, vertical seam delta {seam:.2f}")
