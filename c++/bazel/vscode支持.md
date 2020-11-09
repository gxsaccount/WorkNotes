1.vi third_party/thrust.BUILD  
2.添加  

    864     http_archive(
    865         name = "com_grail_bazel_compdb",
    866         sha256 = "b705be6f45f009436869b67214610fae0805a34649302124e9fef67c7cb0c8bf",
    867         strip_prefix = "bazel-compilation-database-master",
    868         urls = ["https://github.com/grailbio/bazel-compilation-database/archive/master.tar.gz"],
    869     )
3.vi megvideo-v2/BUILD  

     15 load("@com_grail_bazel_compdb//:aspects.bzl", "compilation_database")

      437 compilation_database(
      438     name = "compdb",
      439     targets = [
      440         "megvideo_v2_dev"
      441     ]
      442 )

4../bazel build -c opt --compiler gcc7_cuda10_1  --copt='-DMGB_ENABLE_JSON=1' --copt='-DMGB_VERBOSE_TYPEINFO_NAME=1' --copt='-DMGB_ENABLE_FASTRUN=1' --copt='-DSPDLOG_ACTIVE_LEVEL=SPDLOG_LEVEL_INFO' --copt='-DMGV_ENABLE_PROFILER' //megvideo-v2:compdb  

5.ln -s bazel-bin/megvideo-v2/compile_commands.json ./    [./为vscode的工作目录]  

6.vscode安装ms-vscode.cpptools插件  

