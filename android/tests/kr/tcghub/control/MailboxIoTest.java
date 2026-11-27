package kr.tcghub.control;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

/** Regression for a documents provider that keeps running after cancellation. */
public final class MailboxIoTest {
    private static void check(boolean condition) {
        if (!condition) throw new AssertionError();
    }

    private static void stall(CountDownLatch entered, CountDownLatch release) {
        entered.countDown();
        for (;;) {
            try {
                release.await();
                return;
            } catch (InterruptedException ignored) {
                // A stalled provider need not honor an interrupt.
            }
        }
    }

    public static void main(String[] args) throws Exception {
        long start = 10_000;
        check(MailboxIo.remaining(start, start, 60_000) == 60_000);
        check(MailboxIo.remaining(start + 59_999, start, 60_000) == 1);
        check(MailboxIo.remaining(start + 60_000, start, 60_000) == 0);
        check(MailboxIo.remaining(start - 2_000, start, 60_000) == 0);
        check(MailboxIo.remaining(start, 0, 60_000) == 0);

        CountDownLatch bothStatus = new CountDownLatch(2);
        CountDownLatch release = new CountDownLatch(1);
        CountDownLatch cancelStarted = new CountDownLatch(1);
        try {
            Future<?> first = MailboxIo.submit(true, () -> stall(bothStatus, release));
            Future<?> second = MailboxIo.submit(true, () -> stall(bothStatus, release));
            check(first != null && second != null);
            check(bothStatus.await(2, TimeUnit.SECONDS));
            check(MailboxIo.submit(true, () -> {}) == null);
            MailboxIo.cancel(first, () -> stall(cancelStarted, release));
            check(cancelStarted.await(2, TimeUnit.SECONDS));
            // Neither a blocked read nor its non-cooperative cancellation can hold a command.
            Future<?> control = MailboxIo.submit(false, () -> {});
            check(control != null);
            control.get(2, TimeUnit.SECONDS);
            MailboxIo.cancel(second, null);
        } finally {
            release.countDown();
        }
        System.out.println("Mailbox I/O deadline, bounded stalls, cancellation and command isolation passed");
    }
}
