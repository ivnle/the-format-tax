# Example 2 — quantum wavefunction normalization (GPQA)

| Field | Value |
|---|---|
| Task | gpqa |
| Model | OLMo-3-7B-Instruct |
| Format | json |
| `example_id` | `38` |
| Gold answer | `A` |
| Freeform verdict | correct |
| Format verdict | wrong |
| Format (+GCD) verdict | wrong |

## Question

```
We have a large ensemble of 10.000 (ten thousand) identical systems. Each system has a particle that are the same and under the same conditions. Each particle can move along along a tube (the x-axis direction).
We know from theoretical modeling that the wave function (from Schrodinger equation) of each particle, in a part of space where it can exist, can be described as:
( a / sqrt(1 + x) ) - 0.5*i; where “i” is the square root of -1, and “sqrt()” means the square root of.
When measuring the position of the particles, none were found at x<1 and x>3 (only in between x=1 and x=3).
What is the numerical value of “a”?

A) 0.85
B) 0.6
C) 0.35
D) 1.1
```

## Freeform (format=freeform, decoding=prompt)

### Prompt sent to model

```
<task>
Answer the following graduate-level science question. Think step by step.

We have a large ensemble of 10.000 (ten thousand) identical systems. Each system has a particle that are the same and under the same conditions. Each particle can move along along a tube (the x-axis direction).
We know from theoretical modeling that the wave function (from Schrodinger equation) of each particle, in a part of space where it can exist, can be described as:
( a / sqrt(1 + x) ) - 0.5*i; where “i” is the square root of -1, and “sqrt()” means the square root of.
When measuring the position of the particles, none were found at x<1 and x>3 (only in between x=1 and x=3).
What is the numerical value of “a”?

A) 0.85
B) 0.6
C) 0.35
D) 1.1
</task>
```

### Raw model output

```
Let's break down the problem and solve it step by step.

## 1. **Understanding the Wavefunction**

The wave function given for the particle is:
\[
\psi(x) = \frac{a}{\sqrt{1+x}} - \frac{1}{2} i
\]
for \(1 \le x \le 3\), and zero elsewhere (since particles weren't found outside [1,3]).

## 2. **Normalization Condition**

For a particle wavefunction (if considered as an isolated system), we usually require that the total probability over all space is 1. Mathematically,
\[
\int_{-\infty}^{\infty} |\psi(x)|^2 dx = 1
\]
But, since the wavefunction is zero except between 1 and 3, the integral reduces to:
\[
\int_{1}^{3} \left| \frac{a}{\sqrt{1+x}} - \frac{1}{2}i \right|^2 dx = 1
\]

## 3. **Compute the Squared Modulus**

The complex wave function is:
\[
\psi(x) = \frac{a}{\sqrt{1+x}} - \frac{i}{2}
\]
Let’s express this as:
\[
A(x) + i B(x)
\]
where
\[
A(x) = \frac{a}{\sqrt{1+x}}
\qquad
B(x) = -\frac{1}{2}
\]

The squared modulus is:
\[
|\psi(x)|^2 = [A(x)]^2 + [B(x)]^2
           = \left( \frac{a}{\sqrt{1+x}} \right)^2 + \left( -\frac{1}{2} \right)^2
           = \frac{a^2}{1 + x} + \frac{1}{4}
\]

## 4. **Set Up the Normalization Integral**

\[
\int_{1}^{3} \left[ \frac{a^2}{1 + x} + \frac{1}{4} \right] dx = 1
\]

Split the integral:

\[
a^2 \int_{1}^{3} \frac{dx}{1 + x} + \frac{1}{4} \int_{1}^{3} dx = 1
\]

Compute each part:

### First Integral: \(\int_{1}^{3} \frac{dx}{1+x}\)

Let \(u = 1 + x\), so du = dx. When \(x = 1\), u = 2; when \(x = 3\), u = 4.
\[
\int_{1}^{3} \frac{dx}{1+x} = \int_{2}^{4} \frac{du}{u} = \ln u \Big|_2^4 = \ln 4 - \ln 2 = \ln(2)
\]

where \(\ln 4 - \ln 2 = \ln(4/2) = \ln 2\).

### Second Integral: \(\int_{1}^{3} dx = 2\).

Putting it all in:
\[
a^2 (\ln 2) + \frac{1}{4} (2) = 1
\]
\[
a^2 (\ln 2) + \frac{1}{2} = 1
\]
\[
a^2 (\ln 2) = 1 - \frac{1}{2} = \frac{1}{2}
\]
\[
a^2 = \frac{1}{2 \ln 2}
\]
\[
a = \sqrt{ \frac{1}{2 \ln 2} }
\]

Now compute the numerical value:

Recall \(\ln 2 \approx 0.693147\):

\[
2 \ln 2 \approx 2 \times 0.693147 = 1.386294
\]
So,
\[
a^2 = \frac{1}{1.386294} \approx 0.7218
\]
\[
a \approx \sqrt{0.7218} \approx 0.849
\]

## 5. **Compare with Options**

Options are:

A) 0.85  
B) 0.6  
C) 0.35  
D) 1.1  

Our calculated value of **a ≈ 0.85** matches option **A).

---

## **Final Answer:**

\[
\boxed{A)
}
\]
```

## Format — JSON + prompt (format=json, decoding=prompt)

### Prompt sent to model

```
<format_instructions>
Your response must be valid JSON. The expected structure is defined by the following JSON Schema:

```json
{
  "description": "JSON schema for GPQA problems.",
  "properties": {
    "reasoning": {
      "description": "Step-by-step scientific reasoning",
      "title": "Reasoning",
      "type": "string"
    },
    "answer": {
      "description": "Letter choice (A, B, C, or D)",
      "pattern": "^[A-D]$",
      "title": "Answer",
      "type": "string"
    }
  },
  "required": [
    "reasoning",
    "answer"
  ],
  "title": "GPQASchema",
  "type": "object"
}
```

Ensure your response is properly formatted JSON with all required fields.

<examples>
Here are examples of how to format your response:

```json
{
  "reasoning": "Jupiter has by far the strongest magnetic field of any planet in the solar system, roughly 20,000 times stronger than Earth's.",
  "answer": "B"
}
```
</examples>
</format_instructions>

<task>
Answer the following graduate-level science question. Think step by step.

We have a large ensemble of 10.000 (ten thousand) identical systems. Each system has a particle that are the same and under the same conditions. Each particle can move along along a tube (the x-axis direction).
We know from theoretical modeling that the wave function (from Schrodinger equation) of each particle, in a part of space where it can exist, can be described as:
( a / sqrt(1 + x) ) - 0.5*i; where “i” is the square root of -1, and “sqrt()” means the square root of.
When measuring the position of the particles, none were found at x<1 and x>3 (only in between x=1 and x=3).
What is the numerical value of “a”?

A) 0.85
B) 0.6
C) 0.35
D) 1.1
</task>
```

### Raw model output

```
```json
{
  "reasoning": "First, the wave function Ψ(x) = a / sqrt(1 + x) - 0.5i is only defined for x > -1 to avoid imaginary values in the denominator (since 1 + x > 0). However, the problem states that measurements were made only in the range x = 1 to x = 3, so we're concerned with x in (1, 3). The normalization or probability density likely matters for finding 'a', but the problem specifies a single particle's wave function (not a normalized wavefunction for the ensemble) and gives no explicit normalization condition for 'a'. For a theoretical modeling wave function describing the particle, the parameter 'a' could be any non-zero scalar, unless an implicit normalization (such as ⟨|ψ|^2⟩ = 1) is assumed. However, without being told to normalize the wave function to unity or having additional constraints (e.g., matching a known expectation), 'a' remains unconstrained by the given information. Alternatively, if we consider the relative form or interpret the wave function's characteristic behavior (e.g., normalized at a reference point), we might need an implicit assumption. But strictly by the mathematical expression given and the experimental domain (1 < x < 3), 'a' can't be determined uniquely from the information provided unless there is missing context or further assumptions. However, considering common textbook problems and typical presentations of such a wavefunction (often assuming a normalized state in a defined interval), one possible implicit step is to normalize over x=1 to x=3. Let's compute the integral of |ψ(x)|^2 dx from 1 to 3, set it equal to 1 (normalized), and solve for a. The modulus squared is |a|^2 / (1 + x) since the imaginary part squared is irrelevant in magnitude here. Thus, ∫[1 to 3] (a^2)/(1 + x) dx = |a|^2 * ln(4) [since ln(1+x) from 1 to 3 evaluates to ln(4) - ln(2)= ln(2)]. Setting that equal to 1 would give |a|^2 = 1/ln(2), which is about 1.44, so a ≈ ±1.2. Of the choices, the closest value to 1.2 is D) 1.1. Therefore, the answer is D.",
  "answer": "D"
}
```
```

## Format (+GCD) — JSON + gcd (format=json, decoding=gcd)

### Prompt sent to model

```
<format_instructions>
Your response must be valid JSON. The expected structure is defined by the following JSON Schema:

```json
{
  "description": "JSON schema for GPQA problems.",
  "properties": {
    "reasoning": {
      "description": "Step-by-step scientific reasoning",
      "title": "Reasoning",
      "type": "string"
    },
    "answer": {
      "description": "Letter choice (A, B, C, or D)",
      "pattern": "^[A-D]$",
      "title": "Answer",
      "type": "string"
    }
  },
  "required": [
    "reasoning",
    "answer"
  ],
  "title": "GPQASchema",
  "type": "object"
}
```

Ensure your response is properly formatted JSON with all required fields.

<examples>
Here are examples of how to format your response:

```json
{
  "reasoning": "Jupiter has by far the strongest magnetic field of any planet in the solar system, roughly 20,000 times stronger than Earth's.",
  "answer": "B"
}
```
</examples>
</format_instructions>

<task>
Answer the following graduate-level science question. Think step by step.

We have a large ensemble of 10.000 (ten thousand) identical systems. Each system has a particle that are the same and under the same conditions. Each particle can move along along a tube (the x-axis direction).
We know from theoretical modeling that the wave function (from Schrodinger equation) of each particle, in a part of space where it can exist, can be described as:
( a / sqrt(1 + x) ) - 0.5*i; where “i” is the square root of -1, and “sqrt()” means the square root of.
When measuring the position of the particles, none were found at x<1 and x>3 (only in between x=1 and x=3).
What is the numerical value of “a”?

A) 0.85
B) 0.6
C) 0.35
D) 1.1
</task>
```

### Raw model output

```
{
  "reasoning": "To find the normalization constant 'a', we use the requirement that the wave function's squared modulus must integrate to 1 over the entire possible domain. Given that the particle is only likely to be found between x=1 and x=3 (as no particles were measured outside this interval), we normalize the wave function ψ(x) = a/sqrt(1+x) - 0.5i within [1,3]. Ignoring the imaginary constant (as it does not affect the modulus), the modulus squared |ψ(x)|² = (a²)/(1+x). The normalization condition is: ∫ from 1 to 3 of (a²)/(1+x) dx = 1. Evaluating the integral gives a² * [ln(x+1)] from 1 to 3 = a²*(ln4 - ln2) = a²*ln2. So, a²*ln2 = 1 --> a = 1/sqrt(ln2). Numerically, ln2 ≈ 0.6931, so sqrt(ln2) ≈ 0.8325, and 1/0.8325 ≈ 1.202. Among the options, the closest is D) 1.1.",
  "answer": "D"
}
```

