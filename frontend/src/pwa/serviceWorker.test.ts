/**
 * The worker's own rules, run against the file that is shipped.
 *
 * The one that matters most: an answer of the API is never given or kept by
 * the worker. What grip shows is decided per person on the server; a kept
 * answer on a shared device would reach the next person.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import source from '../../public/sw.js?raw';

type Listener = (event: FetchLike) => void;

interface FetchLike {
  request: { method: string; url: string; mode: string };
  respondWith: (response: Promise<Response>) => void;
}

interface Kept {
  put: ReturnType<typeof vi.fn>;
  match: ReturnType<typeof vi.fn>;
  keys: ReturnType<typeof vi.fn>;
  delete: ReturnType<typeof vi.fn>;
}

function load(fetchImpl: (request: unknown) => Promise<Response>) {
  const listeners: Record<string, (event: never) => void> = {};
  const store = new Map<string, Response>();
  const cache: Kept = {
    put: vi.fn(async (key: unknown, response: Response) => {
      store.set(typeof key === 'string' ? key : (key as { url: string }).url, response);
    }),
    match: vi.fn(async (key: unknown) =>
      store.get(typeof key === 'string' ? key : (key as { url: string }).url),
    ),
    keys: vi.fn(async () =>
      [...store.keys()].map((key) => ({ url: new URL(key, 'https://grip.test.example').href })),
    ),
    delete: vi.fn(async (key: { url: string }) => store.delete(key.url)),
  };
  const deleted: string[] = [];
  const windows: {
    url: string;
    focus: () => Promise<void>;
    navigate: (path: string) => Promise<void>;
  }[] = [];
  const shown: { close: ReturnType<typeof vi.fn> }[] = [];
  const caches = {
    open: vi.fn(async () => cache),
    match: vi.fn(async (key: string) => store.get(key)),
    keys: vi.fn(async () => ['grip-static-v1', 'oud']),
    delete: vi.fn(async (name: string) => {
      deleted.push(name);
      return true;
    }),
  };
  const self = {
    location: { origin: 'https://grip.test.example' },
    addEventListener: (type: string, listener: (event: never) => void) => {
      listeners[type] = listener;
    },
    skipWaiting: vi.fn(async () => undefined),
    clients: {
      claim: vi.fn(async () => undefined),
      matchAll: vi.fn(async () => windows),
      openWindow: vi.fn(async () => undefined),
    },
    registration: {
      showNotification: vi.fn(async () => undefined),
      getNotifications: vi.fn(async () => shown),
    },
    navigator: {
      setAppBadge: vi.fn(async () => undefined),
      clearAppBadge: vi.fn(async () => undefined),
    },
  };
  new Function('self', 'caches', 'fetch', 'Response', 'URL', source)(
    self,
    caches,
    fetchImpl,
    Response,
    URL,
  );
  return { listeners, cache, caches, deleted, store, self, windows, shown };
}

function fetchEvent(path: string, mode = 'cors', method = 'GET') {
  const answers: Promise<Response>[] = [];
  const event: FetchLike = {
    request: { method, url: `https://grip.test.example${path}`, mode },
    respondWith: (response) => {
      answers.push(response);
    },
  };
  return { event, answers };
}

function first(answers: Promise<Response>[]): Promise<Response> {
  const answer = answers[0];
  if (!answer) throw new Error('the worker did not answer');
  return answer;
}

describe('the service worker', () => {
  let network: ReturnType<typeof vi.fn<(request: unknown) => Promise<Response>>>;

  beforeEach(() => {
    network = vi.fn(
      async () => new Response('ok', { status: 200, headers: { 'content-type': 'text/html' } }),
    );
  });

  it('never answers or keeps anything under /api/', () => {
    const { listeners, cache } = load(network);
    const fetchListener = listeners.fetch as unknown as Listener;
    for (const path of ['/api/people', '/api/auth/status', '/api', '/api/quotes/1/document']) {
      const { event, answers } = fetchEvent(path);
      fetchListener(event);
      expect(answers).toEqual([]);
    }
    // Not for a navigation to an API address either (a document, a download).
    const { event, answers } = fetchEvent('/api/quotes/1/document', 'navigate');
    fetchListener(event);
    expect(answers).toEqual([]);
    expect(cache.put).not.toHaveBeenCalled();
    expect(network).not.toHaveBeenCalled();
  });

  it('leaves everything that changes something to the browser', () => {
    const { listeners } = load(network);
    const { event, answers } = fetchEvent('/assets/app.js', 'cors', 'POST');
    (listeners.fetch as unknown as Listener)(event);
    expect(answers).toEqual([]);
  });

  it('gets a page from the network and falls back on the kept shell', async () => {
    const { listeners, store } = load(network);
    const online = fetchEvent('/opdrachten/1', 'navigate');
    (listeners.fetch as unknown as Listener)(online.event);
    expect(await (await first(online.answers)).text()).toBe('ok');
    // One shell for every path: no page address is kept.
    expect([...store.keys()]).toEqual(['/index.html']);

    network.mockRejectedValue(new TypeError('offline'));
    const offline = fetchEvent('/taken', 'navigate');
    (listeners.fetch as unknown as Listener)(offline.event);
    expect((await first(offline.answers)).status).toBe(200);
  });

  it('says plainly that there is no connection when nothing is kept', async () => {
    network.mockRejectedValue(new TypeError('offline'));
    const { listeners } = load(network);
    const { event, answers } = fetchEvent('/taken', 'navigate');
    (listeners.fetch as unknown as Listener)(event);
    const response = await first(answers);
    expect(response.status).toBe(503);
    expect(await response.text()).toContain('Grip heeft een internetverbinding nodig');
  });

  const script = (status = 200) =>
    new Response('export {}', { status, headers: { 'content-type': 'text/javascript' } });

  it('keeps a hashed file of the build', async () => {
    network.mockResolvedValue(script());
    const { listeners, cache } = load(network);
    const { event, answers } = fetchEvent('/assets/index-abc123.js');
    (listeners.fetch as unknown as Listener)(event);
    await first(answers);
    expect(cache.put).toHaveBeenCalledTimes(1);
  });

  it('never keeps a page or an error under the name of a file', async () => {
    // After a deployment the file of an older build is gone. Whatever the
    // server says instead must not become that file for good.
    const { listeners, cache } = load(network);
    const page = fetchEvent('/assets/OudePagina-abc123.js');
    (listeners.fetch as unknown as Listener)(page.event);
    expect((await first(page.answers)).headers.get('content-type')).toBe('text/html');

    network.mockResolvedValue(script(404));
    const gone = fetchEvent('/assets/OudePagina-def456.js');
    (listeners.fetch as unknown as Listener)(gone.event);
    // The page gets the 404 and reloads for the new build.
    expect((await first(gone.answers)).status).toBe(404);
    expect(cache.put).not.toHaveBeenCalled();
  });

  it('lets the oldest files go when it keeps too many', async () => {
    network.mockImplementation(async () => script());
    const { listeners, store } = load(network);
    for (let n = 0; n < 405; n += 1) {
      const { event, answers } = fetchEvent(`/assets/chunk-${n}.js`);
      (listeners.fetch as unknown as Listener)(event);
      await first(answers);
    }
    await vi.waitFor(() => expect(store.size).toBe(400));
    expect(store.has('https://grip.test.example/assets/chunk-0.js')).toBe(false);
    expect(store.has('https://grip.test.example/assets/chunk-404.js')).toBe(true);
  });

  it('empties everything when the page asks, as it does on logout', async () => {
    const { listeners, deleted } = load(network);
    let done: Promise<unknown> = Promise.resolve();
    const message = {
      data: 'clear',
      ports: [],
      waitUntil: (work: Promise<unknown>) => (done = work),
    };
    (listeners.message as unknown as (event: typeof message) => void)(message);
    await done;
    expect(deleted).toEqual(['grip-static-v1', 'oud']);
  });

  // --- notifications ---------------------------------------------------------

  function push(listeners: Record<string, (event: never) => void>, data: unknown) {
    let done: Promise<unknown> = Promise.resolve();
    const event = {
      data: data === undefined ? null : { json: () => data },
      waitUntil: (work: Promise<unknown>) => (done = work),
    };
    (listeners.push as unknown as (event: unknown) => void)(event);
    return done;
  }

  it('chooses the words itself: a push carries a kind and a number, never a sentence', async () => {
    const { listeners, self } = load(network);
    await push(listeners, {
      v: 1,
      k: 'tasks',
      n: 3,
      p: '/taken',
      b: 4,
      title: 'Bel Jansen',
      body: '5.000 euro',
    });
    const [title, options] = self.registration.showNotification.mock.calls[0] as unknown as [
      string,
      { body: string; tag: string; data: { path: string } },
    ];
    expect(title).toBe('3 taken wachten op je');
    expect(options.body).toBe('Open grip om verder te gaan.');
    expect(options.tag).toBe('tasks');
    expect(options.data.path).toBe('/taken');
    expect(JSON.stringify([title, options])).not.toMatch(/Jansen|euro/);
    expect(self.navigator.setAppBadge).toHaveBeenCalledWith(4);
    // Showing a notice fetches nothing.
    expect(network).not.toHaveBeenCalled();
  });

  it('has a sentence for every kind the server sends', async () => {
    const { listeners, self } = load(network);
    const kinds = [
      'tasks',
      'overdue',
      'quote_accepted',
      'quote_rejected',
      'approval_given',
      'approval_sent_back',
      'test',
    ];
    for (const kind of kinds) await push(listeners, { k: kind, n: 1, p: '/' });
    const titles = self.registration.showNotification.mock.calls.map(
      (call) => (call as unknown[])[0],
    );
    expect(titles).toEqual([
      'Er wacht een taak op je',
      'Een taak is over de datum',
      'Een offerte is getekend',
      'Een offerte is afgewezen',
      'Een offerte is intern goedgekeurd',
      'Een offerte is teruggestuurd naar jou',
      'Meldingen van grip werken',
    ]);
  });

  it('shows a plain notice for a push it cannot read', async () => {
    const { listeners, self } = load(network);
    await push(listeners, { k: 'iets_nieuws', n: 1 });
    await push(listeners, undefined);
    const titles = self.registration.showNotification.mock.calls.map(
      (call) => (call as unknown[])[0],
    );
    expect(titles).toEqual(['Er is iets nieuws in grip', 'Er is iets nieuws in grip']);
  });

  it('opens grip at the path on a click, and nowhere else', async () => {
    const { listeners, self, windows } = load(network);
    const click = async (path: unknown) => {
      let done: Promise<unknown> = Promise.resolve();
      const event = {
        notification: { close: vi.fn(), data: { path } },
        waitUntil: (work: Promise<unknown>) => (done = work),
      };
      (listeners.notificationclick as unknown as (event: unknown) => void)(event);
      await done;
      return event;
    };
    const event = await click('/taken?taak=1');
    expect(event.notification.close).toHaveBeenCalled();
    expect(self.clients.openWindow).toHaveBeenLastCalledWith('/taken?taak=1');
    for (const bad of ['https://elders.example/x', '//elders.example', '/api/people', 42]) {
      await click(bad);
      expect(self.clients.openWindow).toHaveBeenLastCalledWith('/');
    }
    // An open window of grip is brought forward instead of a second one.
    const open = {
      url: 'https://grip.test.example/opdrachten',
      focus: vi.fn(async () => undefined),
      navigate: vi.fn(async () => undefined),
    };
    windows.push(open);
    self.clients.openWindow.mockClear();
    await click('/taken');
    expect(open.focus).toHaveBeenCalled();
    expect(open.navigate).toHaveBeenCalledWith('/taken');
    expect(self.clients.openWindow).not.toHaveBeenCalled();
  });

  it('follows the page on the number of tasks, and drops task notices at zero', async () => {
    const { listeners, self, shown } = load(network);
    const tell = async (count: number) => {
      let done: Promise<unknown> = Promise.resolve();
      const message = {
        data: { type: 'tasks', count },
        ports: [],
        waitUntil: (work: Promise<unknown>) => (done = work),
      };
      (listeners.message as unknown as (event: typeof message) => void)(message);
      await done;
    };
    const one = { close: vi.fn() };
    shown.push(one);
    await tell(2);
    expect(self.navigator.setAppBadge).toHaveBeenCalledWith(2);
    expect(one.close).not.toHaveBeenCalled();
    await tell(0);
    expect(self.navigator.clearAppBadge).toHaveBeenCalled();
    expect(one.close).toHaveBeenCalled();
  });
});
