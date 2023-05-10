#!/bin/bash
export PATH=/opt/deeproute/perf-analysis/perf-collector/bin:$PATH
CUR_DIR=$(dirname $(readlink -f "$0"))
FLAME_DIR=/opt/deeproute/perf-analysis/perf-collector/FlameGraph
START_TIME=$(date +%Y%m%d%H%M%S)
DATA_DIR=/opt/deeproute/perfdata/perf_$START_TIME
WORK_DIR="/tmp/starter/log/perf"
prepare_env()
{
    [ ! -d ${WORK_DIR} ] && mkdir -p ${WORK_DIR}
    [ ! -d ${DATA_DIR} ] && mkdir -p ${DATA_DIR}
}

perf_module()
{
    cd $DATA_DIR
    echo $PATH
    echo "Flame dir is ${FLAME_DIR}"
    if [ "$MODULE_NAME" == "all" ];then
	    echo "Get all process's perf data "
    else
        if [ "${RUNNING_PID}" == "0" ]; then
            RUNNING_PID=`pidof $1 | awk '{print $1}'`
        fi
        echo "Perf record for pid ${RUNNING_PID},module is $1"
    fi
    if [ "${RUNNING_PID}" != "0" ]; then
        echo -e "\033[32m perf record -a -F ${PERF_FREQ} --call-graph dwarf -p ${RUNNING_PID} -o ${MODULE_NAME}_${RUNNING_PID}.data -- sleep ${PERF_PERIOD} \033[0m"
        perf record -a -F ${PERF_FREQ} --call-graph dwarf -p ${RUNNING_PID} -o ${MODULE_NAME}_${RUNNING_PID}.data -- sleep ${PERF_PERIOD}
        perf script -i ${MODULE_NAME}_${RUNNING_PID}.data > ${MODULE_NAME}_${RUNNING_PID}.perf
        cp -a ${MODULE_NAME}_${RUNNING_PID}.perf ${FLAME_DIR}
    else
        echo -e "\033[32m perf record -a -F ${PERF_FREQ} --call-graph dwarf -- sleep ${PERF_PERIOD}  \033[0m"
        perf record -a -F ${PERF_FREQ} --call-graph dwarf -- sleep ${PERF_PERIOD}
        perf script > ${MODULE_NAME}.perf
        cp -a ${MODULE_NAME}.perf ${FLAME_DIR}
    fi
    cd -

    cd ${FLAME_DIR}
    if [ "${RUNNING_PID}" != "0" ];then
        ./stackcollapse-perf.pl ${MODULE_NAME}_${RUNNING_PID}.perf > out.folded
        ./flamegraph.pl out.folded > ${MODULE_NAME}_${RUNNING_PID}_${START_TIME}.svg
        cp -a ${MODULE_NAME}_${RUNNING_PID}_${START_TIME}.svg ${WORK_DIR}
    else
        ./stackcollapse-perf.pl ${MODULE_NAME}.perf > out.folded
        ./flamegraph.pl out.folded > ${MODULE_NAME}_${START_TIME}.svg
        cp -a ${MODULE_NAME}_${START_TIME}.svg ${WORK_DIR}
    fi
    cd -
    echo "perf analyse ${MODULE_NAME} success, the svg file is located in ${WORK_DIR}/${MODULE_NAME}_${RUNNING_PID}_${START_TIME}.svg"
}

clean_world()
{
    rm -rf ${DATA_DIR}
    rm ${FLAME_DIR}/out.folded
    rm ${FLAME_DIR}/*.perf
    rm ${FLAME_DIR}/*.svg
}

default_params()
{
    PERF_PERIOD=60      # Period of perf recording ,default 60 sec
    PERF_FREQ=999       # frequency, default 999 
    RUNNING_PID=0       # default pid 
}

usage()
{
    echo "$0 <module_name> [OPTIONS] [ARGS]"
    echo ""
    echo " module_name : the process name running in the system,such as perception_node\frame_test\canbus_node"
    echo " OPTIONS:"
    echo " -h : print usage info "
    echo " -t : the duration of the perf recording in seconds,defualt is 60 secs "
    echo " -f : the frequency of the perf recording,defualt is 999 "
    echo " -p : the specify pid of perf recording ,higher priority then module name "
}

check_user()
{
    user=`whoami`
    if [ "$user" != "root" ]; then
        echo "Permission denied, please using the perf.sh as user root or sudo"
        exit $E_NOTROOT
    fi
}

check_user

if [ $# -lt 1 ];then
    usage && exit 0
else
    MODULE_NAME=$1
    if [ "$1" == "-h" ];then
        usage && exit 0
    else
        default_params
        shift
        while getopts "h:t:f:p:" arg; do
        case $arg in
            h)
            echo "usage" 
            usage
            ;;
            t)
            PERF_PERIOD=$OPTARG
            echo "Perf record will last for " $PERF_PERIOD "seconds"
            ;;
            f)
            PERF_FREQ=$OPTARG
            echo "Perf frequency is  " $PERF_FREQ
            ;;
            p)
            RUNNING_PID=$OPTARG
            echo "Perf will record the pid $RUNNING_PID"
            ;;
        esac
        done
    fi
fi

prepare_env
perf_module ${MODULE_NAME}
clean_world
