    
    #include <npp.h>
    #include <stdio.h>
    #include <stdlib.h>
    #include <time.h>
    #include <string.h>
    #include <nppi_support_functions.h>

    //nvcc npp_test.cpp -I/mnt/data/gitlab-ci/cuda-10.0/cuda/include  -L/mnt/data/gitlab-ci/cuda-10.0/cuda/lib64/ -lnppisu_static -lnppicc_static -lnppial_static -lnppc_static -lnppif_static -lnppig_static -lnppim_static -lnppicom_static -lculibos -lcublas_static -lcuda -lcudart -o npp_test

    int main()
    {


      
      char *char_frame;
      char_frame = (char *)malloc(sizeof(char) * 1920 * 1080 * 3);
      memset(char_frame, 1, 1920 * 1080 * 3);
      //cpu buffer that will hold converted data
      Npp8u *converted_data = (Npp8u *)malloc(1920*1080*3);
      memset(converted_data, 0, 1080 * 1920 * 3);

      //Begin - load data and convert rgb to yuv
      {
          NppStatus ret = NPP_SUCCESS;
          int stepSource;
          Npp8u *frame = nppiMalloc_8u_C3(1920, 1080, &stepSource);
          cudaMemcpy2D(frame, stepSource, char_frame, 0, 1920, 1080, cudaMemcpyHostToDevice);

          int stepDestP1, stepDestP2, stepDestP3;
          Npp8u *m_stYuvP1 = nppiMalloc_8u_C1(1920, 1080, &stepDestP1);
          Npp8u *m_stYuvP2 = nppiMalloc_8u_C1(1920, 1080, &stepDestP2);
          Npp8u *m_stYuvP3 = nppiMalloc_8u_C1(1920, 1080, &stepDestP3);
          int d_steps[3] = {stepDestP1, stepDestP2, stepDestP3};
          Npp8u *d_ptrs[3] = {m_stYuvP1, m_stYuvP2, m_stYuvP3};

          NppiSize ROI = {1920, 1080};

          clock_t start,end;
          double  duration = 0.0;

          start =clock();
          nppiRGBToYUV_8u_C3P3R(frame, stepSource, d_ptrs, stepDestP1, ROI);


          // nppiYUVToRGB_8u_P3R();
          end =clock();
          duration = (double)(end - start) / CLOCKS_PER_SEC;
          printf( "%f seconds\n", duration );
          cudaMemcpy2D(converted_data, 1920, m_stYuvP1, stepDestP1, 1920, 1080, cudaMemcpyDeviceToHost);
          }
          return 0;
      }
