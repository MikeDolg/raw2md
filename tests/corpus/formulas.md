# Formulas and derivations

The section checks that mathematical markup survives: inline formulas and
display formulas on a line of their own. Prose surrounds the formulas, so that
recognition works under realistic conditions.

## Inline formulas

The rest energy of a body relates to its mass by $E = mc^2$, where $c$ is the
speed of light. The area of a circle of radius $r$ is $S = \pi r^2$, and the
circumference is $L = 2 \pi r$. The roots of a quadratic equation follow from
$x_{1,2} = \frac{-b \pm \sqrt{b^2 - 4ac}}{2a}$.

## Display formulas

The definite integral of the exponential function on the positive half-axis:

$$\int_0^{\infty} e^{-x} \, dx = 1.$$

The sum of a geometric series for $|q| < 1$:

$$\sum_{n=0}^{\infty} q^{n} = \frac{1}{1 - q}.$$

The arithmetic mean of a set of $N$ values:

$$\bar{x} = \frac{1}{N} \sum_{i=1}^{N} x_i.$$

## Greek letters and subscripts

The normal distribution has the parameters $\mu$ and $\sigma$, and its density is:

$$f(x) = \frac{1}{\sigma \sqrt{2\pi}} \, e^{-\frac{(x - \mu)^2}{2\sigma^2}}.$$

Ohm's law for a circuit section reads $I = \frac{U}{R}$, and the power reads
$P = U I = I^2 R$.

## Formula edge cases

### Escaped dollar sign

In the text, prices and sums are written as \$100, \$200 – the escaped sign is
not a formula boundary and the counter does not count it.

### Deeply nested fractions

The derivative of a compound fraction is an example of deep bracket nesting:

$$\frac{\partial}{\partial x}\!\left(\frac{\sqrt{a^2 + x^2}}{\sqrt{b^2 - x^2}}\right)
= \frac{x(b^2 - x^2) + x(a^2 + x^2)}{(b^2 - x^2)^{3/2}\sqrt{a^2 + x^2}}.$$

### Multi-line display formula

A system of equations is written as one display formula with its rows split by
a line break:

$$\begin{cases}
a_{11} x_1 + a_{12} x_2 = b_1, \\
a_{21} x_1 + a_{22} x_2 = b_2.
\end{cases}$$

### Delimiters on separate lines

Some sources put the opening and the closing `$$` on lines of their own, with
no formula text on the same line:

$$
v^2 = v_0^2 + 2 a s
$$
