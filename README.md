# PyASL: GUI-Based ASL Pipeline Execution & Visualization
<img width="1071" height="113" alt="image" src="https://github.com/user-attachments/assets/dd8867bc-9659-4880-8512-e1d92f423735" />


PyASL is an open-source Python library for processing arterial spin labeling (ASL) MRI data. This GSoC contribution focuses on improving the PyASL application with a user-friendly GUI for pipeline execution, batch processing, and visualization of NumPy-based outputs.

## Features

-  **GUI-based pipeline execution**
-  **Batch processing** of large numbers of output files
-  **(NEW!) NumPy visualization** for inspecting processing results
-  **(NEW!) Background processing** keeps the application responsive
-  **(NEW!) Automatic gallery updates** when pipeline processing finishes
-  Visualization support for both **light and dark application themes**
-  **Ready-to-use image exports** for sharing results

## Engineering Highlights

- Visualization tasks are processed in the background so the GUI remains responsive.
- The results gallery is automatically updated when a pipeline completes.
- The application efficiently handles large batches of output files.
- Visualizations adapt automatically to the application's light and dark themes.
- The workflow allows users to inspect pipeline outputs without writing additional Python scripts.

## Project Impact

-  Removes the need to write Python scripts to inspect output files.
-  Makes it easier to visually verify ASL processing results.
-  Reduces the time required to review large batches of outputs.
-  Simplifies sharing results through ready-to-use image exports.

## Documentation

 Tutorials and documentation will provide guidance for running pipelines, processing batches, and visualizing generated results.

## GSoC

This work was developed as part of **Google Summer of Code (GSoC)** with the **Open Science Initiative for Perfusion Imaging (OSIPI)**.

## License

This project is licensed under the MIT License – see the `LICENSE` file for details.
