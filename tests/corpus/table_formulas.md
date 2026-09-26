# Tables with formulas and a sized figure

The section reproduces the layout of engineering theses and papers: a table
whose column carries a formula – display or inline – and a figure with a set
inset size.

## Table of computed quantities

Some rows carry a display formula, some an inline one; in the source documents
such a table numbers the equations.

| No. | Quantity           | Formula                                                           |
|-----|--------------------|-------------------------------------------------------------------|
| 1   | Relative deviation | $$\Delta\varepsilon,\ \% = \frac{h_i - h_0}{h_0} \cdot 100$$      |
| 2   | Mean value         | $\bar{x} = \frac{1}{N}\sum_{i=1}^{N} x_i$                         |
| 3   | Measurement number | $i$                                                               |
| 4   | Error              | $$\sigma = \sqrt{\frac{1}{N-1}\sum_{i=1}^{N} (x_i - \bar{x})^2}$$ |

## Figure with explicit size

The diagram below sets the inset size with the `width`/`height` attributes – in
a DOCX conversion this becomes an HTML image tag with a style instead of an
ordinary markdown link.

![Deviation diagram](assets/chart.png){width=300px height=200px}

The mean value on the chart repeats the symbol from the table – $\bar{x}$.
