# Embedded images

The section checks that media content survives conversion: images are
extracted into a separate folder, the relative links stay correct, and the
media files are graded for quality.

## Sample image

![Sample](assets/sample.png)

The image holds a colour gradient and simple geometric shapes. It checks that
the conversion engine extracts images correctly and writes relative links of
the form `file_name/name.png`.

## Diagram

![Diagram](assets/chart.png)

A drawing with a grid and a bar chart. Together with the sample above it checks:

- that both images land in one media folder next to the result;
- that the links still work after conversion;
- that the size of the extracted files is above the threshold (512 bytes).
