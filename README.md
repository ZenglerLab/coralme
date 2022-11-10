![logo](https://github.com/jdtibochab/coralme/blob/main/docs/logo.png)
coralME
=======

The **COmprehensive Reconstruction ALgorithm for ME-models (coralME)** is an automatic pipeline for the reconstruction of ME-models. coralME integrates existing ME-modeling packages `COBRAme`_, `ECOLIme`_, and `solveME`_, generalizes their functions for implementation on any prokaryote, and processes readily available organism-specific inputs for the automatic generation of a working ME-model.

coralME has four main objectives:

1. **Synchronize** input files to remove contradictory entries.
2. **Complement** input files from homology with a template organism to complete the E-matrix.
3. **Build** a working ME-model
4. **Inform** the user about necessary steps to curate the ME-model.

The DockerHub images contain a precompiled version the qMINOS solver and SoPlex can additionally be installed if a Docker container is build locally.

Installation
------------

1. pip install coralme