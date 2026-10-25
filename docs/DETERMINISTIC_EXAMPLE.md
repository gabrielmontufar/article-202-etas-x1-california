# Deterministic numerical example

Install the two packages in requirements-example.txt in an isolated Python environment, then run:

    python examples/deterministic_kernel_example.py

Optional argument: --fixture PATH to an input JSON matching examples/deterministic_fixture.json. Output is JSON on standard output; no scientific result files are written. A failed tolerance check raises an exception and returns failure.

The example imports the preserved original temporal and radial CDF functions and polygon integrator. The temporal case uses p=2, giving F(t)=t/(c+t) for t>=0. The radial case uses q=2, giving F(r)=r^2/(d^2+r^2). The centred unit-variance Gaussian mass in the square [-1,1]^2 equals erf(1/sqrt(2))^2. These analytic values, fixed before the run, are compared at absolute tolerance 1e-12. Coordinates are dummy Cartesian coordinates; no network boundary is required.

This is a reusable numerical-kernel example and installation smoke check, not a rerun of the natural experiment or a Monte Carlo simulation. It draws no random values, fits no parameters, computes no IG, changes no decision, and does not resolve H08. A clean environment installation is not claimed merely because an existing local environment runs the example.
