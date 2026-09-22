#include "../reference_check.hpp"

#include <cassert>
#include <vector>

namespace {

void test_nt()
{
  int constexpr m = 2;
  int constexpr n = 3;
  int constexpr k = 4;
  int constexpr ld_a = m;
  int constexpr ld_b = n;
  int constexpr ld_c = m;

  std::vector<float> a(m * k);
  std::vector<float> b(n * k);
  std::vector<float> initial_c(m * n, 2.0f);
  std::vector<float> result(m * n);

  for (int reduction = 0; reduction < k; ++reduction) {
    for (int row = 0; row < m; ++row) {
      a[row + reduction * ld_a] = float(row + 2 * reduction);
    }
    for (int col = 0; col < n; ++col) {
      b[col + reduction * ld_b] = float(3 * col - reduction);
    }
  }

  for (int col = 0; col < n; ++col) {
    for (int row = 0; row < m; ++row) {
      float sum = 0.0f;
      for (int reduction = 0; reduction < k; ++reduction) {
        sum += a[row + reduction * ld_a] *
               b[col + reduction * ld_b];
      }
      result[row + col * ld_c] = 1.5f * sum + 0.25f * 2.0f;
    }
  }

  assert(cute_tutorial::check_gemm_result(
      m, n, k, 'N', 'T',
      1.5f, a, ld_a, b, ld_b,
      0.25f, initial_c, ld_c, result,
      {1.0e-6, 1.0e-6}, false));
}

void test_tn_and_failure()
{
  int constexpr m = 3;
  int constexpr n = 2;
  int constexpr k = 4;
  int constexpr ld_a = k;
  int constexpr ld_b = k;
  int constexpr ld_c = m;

  std::vector<float> a(m * k);
  std::vector<float> b(n * k);
  std::vector<float> initial_c(m * n, -1.0f);
  std::vector<float> result(m * n);

  for (int row = 0; row < m; ++row) {
    for (int reduction = 0; reduction < k; ++reduction) {
      a[row * ld_a + reduction] = float(row + reduction);
    }
  }
  for (int col = 0; col < n; ++col) {
    for (int reduction = 0; reduction < k; ++reduction) {
      b[col * ld_b + reduction] = float(2 * col + reduction);
    }
  }

  for (int col = 0; col < n; ++col) {
    for (int row = 0; row < m; ++row) {
      float sum = 0.0f;
      for (int reduction = 0; reduction < k; ++reduction) {
        sum += a[row * ld_a + reduction] *
               b[col * ld_b + reduction];
      }
      result[row + col * ld_c] = sum;
    }
  }

  assert(cute_tutorial::check_gemm_result(
      m, n, k, 'T', 'N',
      1.0f, a, ld_a, b, ld_b,
      0.0f, initial_c, ld_c, result,
      {1.0e-6, 1.0e-6}, false));

  result[2] += 10.0f;
  assert(!cute_tutorial::check_gemm_result(
      m, n, k, 'T', 'N',
      1.0f, a, ld_a, b, ld_b,
      0.0f, initial_c, ld_c, result,
      {1.0e-6, 1.0e-6}, false));
}

} // 匿名命名空间结束

int main()
{
  test_nt();
  test_tn_and_failure();
  return 0;
}
