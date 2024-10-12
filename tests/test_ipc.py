from liteyuki.comm import Channel as Chan
from multiprocessing import Process


def p1(chan: Chan):
    for i in range(10):
        chan.send(i)


def p2(chan: Chan):
    while True:
        print(chan.recv())


def test_ipc():
    chan = Chan("Name")

    p1_proc = Process(target=p1, args=(chan,))
    p2_proc = Process(target=p2, args=(chan,))

    p1_proc.start()
    p2_proc.start()
