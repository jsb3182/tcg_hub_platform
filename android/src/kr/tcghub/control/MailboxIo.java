package kr.tcghub.control;

import java.util.concurrent.Future;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.SynchronousQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

/** A stalled status provider call cannot queue a power command behind it. */
final class MailboxIo {
    private static final ThreadPoolExecutor STATUS = pool("hub-status");
    private static final ThreadPoolExecutor COMMANDS = pool("hub-command");
    private static final ThreadPoolExecutor CANCELLATIONS = pool("hub-cancel");

    private static ThreadPoolExecutor pool(String name) {
        return new ThreadPoolExecutor(0, 2, 30, TimeUnit.SECONDS, new SynchronousQueue<>(), task -> {
            Thread thread = new Thread(task, name);
            thread.setDaemon(true);
            return thread;
        });
    }

    static Future<?> submit(boolean status, Runnable job) {
        try {
            return (status ? STATUS : COMMANDS).submit(job);
        } catch (RejectedExecutionException busy) {
            return null;
        }
    }

    static void cancel(Future<?> operation, Runnable cancelRead) {
        if (operation == null && cancelRead == null) return;
        try {
            CANCELLATIONS.execute(() -> {
                if (operation != null) operation.cancel(true);
                if (cancelRead != null) cancelRead.run();
            });
        } catch (RejectedExecutionException busy) {
            // The UI has already detached the request. Even provider cancellation may stall.
        }
    }

    static long remaining(long now, long started, long timeout) {
        long age = now - started;
        if (started <= 0 || timeout <= 0 || timeout > 12 * 60_000 || age < -1000 || age >= timeout) return 0;
        return timeout - Math.max(0, age);
    }

    private MailboxIo() {}
}
