# Chapter 4: Thinking with Data

Statistics is the science of learning from data. This chapter introduces the
core vocabulary every data reader needs: how to summarize a batch of numbers,
how to quantify their spread, and how to reason from a small Sample to a
large Population.

## 4.1 Two branches of statistics

Descriptive Statistics summarizes what the data show. A teacher who reports
the class average, or a coach who charts lap times, is doing Descriptive
Statistics: no claims are made beyond the numbers at hand.

Inferential Statistics goes further. It uses a Sample, a manageable subset,
to draw conclusions about a Population, the full group of interest. Because
the Sample is only part of the Population, every inference carries
uncertainty, which Probability quantifies.

Good Sampling is the bridge between the two branches. In good Sampling every
member of the Population has a known chance of selection. Sampling Bias
arises when some members are systematically over- or under-represented, and
it silently corrupts every conclusion drawn from the data.

## 4.2 Central Tendency

Central Tendency asks where the middle of the data lies. The Mean is the
arithmetic average: add every value and divide by how many there are. The
Median is the middle value after sorting, and the Mode is the value that
appears most often.

Each measure has a temperament. The Mean uses every value but is pulled by
extremes. The Median resists extremes, which makes it the honest reporter
for skewed income data. The Mode is the only choice for categories, such as
favorite color, where averaging makes no sense.

## 4.3 Dispersion and shape

Dispersion describes how far values stray from the center. Variance is the
average squared distance from the Mean, and the Standard Deviation is its
square root, back in the original units. A small Standard Deviation means
the values cluster tightly; a large one means they sprawl.

Many natural measurements follow the Normal Distribution, the familiar
bell curve fully described by its Mean and Standard Deviation. Under the
Normal Distribution, about two thirds of values fall within one Standard
Deviation of the Mean.

An Outlier is a value far from the rest. An Outlier may reveal a discovery
or a data-entry error, so every Outlier deserves investigation before any
decision is made.

## 4.4 From description to inference

Hypothesis Testing turns questions into wagers. We state a Null Hypothesis,
usually a claim of no effect, and ask whether the data contradict it. The
P-Value is the Probability of seeing data this extreme if the Null
Hypothesis were true. A small P-Value casts doubt on the Null Hypothesis,
but it never proves the alternative.

A Confidence Interval reports a plausible range for an unknown quantity,
such as the Mean of a Population. Wider intervals reflect greater
uncertainty; larger Samples earn narrower ones.

Finally, Correlation measures how two variables move together, while
Regression models one variable as a function of another. Neither one, on
its own, establishes causation: Correlation quantifies association, and
only careful design separates cause from coincidence.
