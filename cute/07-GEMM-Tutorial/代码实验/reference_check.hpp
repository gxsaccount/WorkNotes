#pragma once

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <iostream>
#include <limits>
#include <type_traits>

namespace cute_tutorial {

struct ResultTolerance {
  double atol;
  double rtol;
};

template <class Output>
constexpr ResultTolerance default_tolerance()
{
  if constexpr (sizeof(Output) <= 2) {
    // The SM80 tutorial uses FP16 accumulation and output.
    return {1.0, 0.10};
  } else {
    return {5.0e-3, 5.0e-3};
  }
}

template <class T>
double as_double(T const& value)
{
  return static_cast<double>(value);
}

template <class HostA, class HostB, class HostC, class HostResult,
          class Alpha, class Beta>
bool check_gemm_result(
    int m, int n, int k,
    char trans_a, char trans_b,
    Alpha alpha,
    HostA const& a, int ld_a,
    HostB const& b, int ld_b,
    Beta beta,
    HostC const& initial_c, int ld_c,
    HostResult const& result,
    ResultTolerance tolerance =
        default_tolerance<typename HostResult::value_type>(),
    bool verbose = true)
{
  if (!((trans_a == 'N' || trans_a == 'T') &&
        (trans_b == 'N' || trans_b == 'T'))) {
    if (verbose) {
      std::cerr << "RESULT_CHECK: invalid transpose flags\n";
    }
    return false;
  }

  double const alpha_d = as_double(alpha);
  double const beta_d = as_double(beta);
  double max_abs_error = 0.0;
  double max_rel_error = 0.0;
  int max_m = 0;
  int max_n = 0;
  std::size_t mismatch_count = 0;
  constexpr std::size_t max_reported_mismatches = 8;

  for (int col = 0; col < n; ++col) {
    for (int row = 0; row < m; ++row) {
      double accumulator = 0.0;

      for (int reduction = 0; reduction < k; ++reduction) {
        std::size_t const a_index =
            trans_a == 'N'
                ? static_cast<std::size_t>(row) +
                      static_cast<std::size_t>(reduction) * ld_a
                : static_cast<std::size_t>(row) * ld_a +
                      static_cast<std::size_t>(reduction);

        std::size_t const b_index =
            trans_b == 'T'
                ? static_cast<std::size_t>(col) +
                      static_cast<std::size_t>(reduction) * ld_b
                : static_cast<std::size_t>(col) * ld_b +
                      static_cast<std::size_t>(reduction);

        accumulator += as_double(a[a_index]) * as_double(b[b_index]);
      }

      std::size_t const c_index =
          static_cast<std::size_t>(row) +
          static_cast<std::size_t>(col) * ld_c;

      double const expected =
          alpha_d * accumulator + beta_d * as_double(initial_c[c_index]);
      double const actual = as_double(result[c_index]);
      double const abs_error = std::abs(actual - expected);
      double const rel_error =
          abs_error / std::max(std::abs(expected),
                               std::numeric_limits<double>::min());

      if (abs_error > max_abs_error) {
        max_abs_error = abs_error;
        max_rel_error = rel_error;
        max_m = row;
        max_n = col;
      }

      double const allowed_error =
          tolerance.atol + tolerance.rtol * std::abs(expected);
      if (abs_error > allowed_error) {
        if (verbose && mismatch_count < max_reported_mismatches) {
          std::cerr
              << "RESULT_CHECK mismatch at (" << row << "," << col << ")"
              << ": expected=" << expected
              << ", actual=" << actual
              << ", abs_error=" << abs_error
              << ", allowed=" << allowed_error << "\n";
        }
        ++mismatch_count;
      }
    }
  }

  if (mismatch_count != 0) {
    if (verbose) {
      std::cerr
          << "RESULT_CHECK: FAIL mismatches=" << mismatch_count
          << ", max_abs_error=" << max_abs_error
          << ", max_rel_error=" << max_rel_error
          << " at (" << max_m << "," << max_n << ")\n";
    }
    return false;
  }

  if (verbose) {
    std::cout
        << "RESULT_CHECK: PASS"
        << " max_abs_error=" << max_abs_error
        << " max_rel_error=" << max_rel_error
        << " at (" << max_m << "," << max_n << ")\n";
  }
  return true;
}

} // namespace cute_tutorial
