**1.先到bazel的workspace中**  
**2.bazel help**
  % bazel help
                             [Bazel release bazel-<version>]
  Usage: bazel <command> <options> ...

  Available commands:
    analyze-profile     Analyzes build profile data.
    aquery              Executes a query on the post-analysis action graph.
    build               Builds the specified targets.
    canonicalize-flags  Canonicalize Bazel flags.
    clean               Removes output files and optionally stops the server.

    cquery              Executes a post-analysis dependency graph query.

    dump                Dumps the internal state of the Bazel server process.

    help                Prints help for commands, or the index.
    info                Displays runtime info about the bazel server.

    fetch               Fetches all external dependencies of a target.
    mobile-install      Installs apps on mobile devices.

    query               Executes a dependency graph query.

    run                 Runs the specified target.
    shutdown            Stops the Bazel server.
    test                Builds and runs the specified test targets.
    version             Prints version information for Bazel.

  Getting more help:
    bazel help <command>
                     Prints help and options for <command>.
    bazel help startup_options
                     Options for the JVM hosting Bazel.
    bazel help target-syntax
                     Explains the syntax for specifying targets.
    bazel help info-keys
                     Displays a list of keys used by the info command.

**bazel build**  
 
    % bazel build 下列命令

    All target patterns starting with // are resolved relative to the current workspace.
    
    //foo/bar:wiz	Just the single target //foo/bar:wiz.
    //foo/bar	Equivalent to //foo/bar:bar.
    //foo/bar:all	All rules in the package foo/bar.
    //foo/...	All rules in all packages beneath the directory foo.
    //foo/...:all	All rules in all packages beneath the directory foo.
    //foo/...:*	All targets (rules and files) in all packages beneath the directory foo.
    //foo/...:all-targets	All targets (rules and files) in all packages beneath the directory foo.

    :foo	Equivalent to //foo:foo.
    bar:wiz	Equivalent to //foo/bar:wiz.
    bar/wiz	Equivalent to: //foo/bar/wiz:wiz if foo/bar/wiz is a package, //foo/bar:wiz if foo/bar is a package, //foo:bar/wiz otherwise.
    bar:all	Equivalent to //foo/bar:all.
    :all	Equivalent to //foo:all.
    ...:all	Equivalent to //foo/...:all.
    ...	Equivalent to //foo/...:all.
    bar/...:all	Equivalent to //foo/bar/...:all.
    
*patterns*  
    
    bazle build //foo/* == //foo/...:all-targets
    bazel build foo/... bar/...  将所有foo和bar的文件build
    bazel build -- foo/... -foo/bar/...  build 所有foo/下的target，除了foo/bar/下的
    
*fetch 外部依赖*  
    
    bazel fetch //...
    在bazel build之前bazel会自动run  
   https://docs.bazel.build/versions/master/guide.html#repository-cache
