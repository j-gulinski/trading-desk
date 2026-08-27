"""Book alpha/beta regression shared by risk reporting."""

MINIMUM_OBSERVATIONS = 20


def alpha_beta(book_returns, benchmark_returns, minimum_observations=MINIMUM_OBSERVATIONS):
    """OLS regression of book returns on aligned benchmark returns."""
    if len(book_returns) != len(benchmark_returns):
        raise ValueError("book and benchmark returns must be aligned")
    empty = {"alpha": None, "beta": None, "r_squared": None}
    observations = len(book_returns)
    if observations < minimum_observations:
        return {**empty, "status": "INSUFFICIENT_DATA"}
    mean_book = sum(book_returns) / observations
    mean_benchmark = sum(benchmark_returns) / observations
    benchmark_variance = (
        sum((value - mean_benchmark) ** 2 for value in benchmark_returns) / observations
    )
    if benchmark_variance == 0:
        return {**empty, "status": "ZERO_BENCHMARK_VARIANCE"}
    book_variance = sum((value - mean_book) ** 2 for value in book_returns) / observations
    covariance = sum(
        (book_value - mean_book) * (benchmark_value - mean_benchmark)
        for book_value, benchmark_value in zip(book_returns, benchmark_returns)
    ) / observations
    beta = covariance / benchmark_variance
    return {
        "alpha": mean_book - beta * mean_benchmark,
        "beta": beta,
        "r_squared": (
            covariance * covariance / (book_variance * benchmark_variance)
            if book_variance > 0
            else None
        ),
        "status": "READY",
    }
