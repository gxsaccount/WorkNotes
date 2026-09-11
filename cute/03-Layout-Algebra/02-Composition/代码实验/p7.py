import cutlass.cute as cute

@cute.jit
def run():
    def show(tag, b):
        cute.printf("[{}] {}\n", tag, b)
    B = cute.make_layout((4,3), stride=(3,1))
    R = cute.make_layout(((2,2),3), stride=((24,2),8))
    A = cute.make_layout((6,2), stride=(8,2))

    show(1,  cute.compatible(B, R))                 # 后置条件：R 装得下 B 的坐标？
    show(2,  cute.compatible(B, B))
    show(3,  cute.compatible(B, cute.make_layout((4,3), stride=(1,4))))   # 同 shape 异 stride
    show(4,  cute.compatible(B, cute.make_layout((12,), stride=(1,))))    # 拍平 12
    show(5,  cute.compatible(B, cute.make_layout((2,6), stride=(1,2))))   # 不同拆分
    show(6,  cute.compatible(B, cute.make_layout((4,3), stride=(3,1))))
    show(7,  cute.compatible(cute.make_layout((4,), stride=(1,)), cute.make_layout(((2,2),), stride=((1,2),))))
    show(8,  cute.compatible(A, B))                 # 前置条件：A 装得下 B 的值域？
    show(9,  cute.size(B))
    show(10, cute.size(R))
    show(11, cute.size(A))
run()
