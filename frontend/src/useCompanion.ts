import { useEffect } from "react";

export function useCompanion() {
  useEffect(() => {
    const connect = () => {
      const id = crypto.randomUUID();
      const connection = new EventSource(`/api/companion/page?page_id=${id}`);
      connection.onmessage = (event) => {
        try {
          if (JSON.parse(event.data).type === "focus") window.focus();
        } catch {
          /* A partial notification must never break the learning page. */
        }
      };
      let closed = false;
      return () => {
        if (closed) return;
        closed = true;
        connection.close();
        void fetch(`/api/companion/page/${id}`, {
          method: "DELETE",
          headers: { "X-BookSide": "1", "X-LearNest": "1" },
          keepalive: true,
        }).catch(() => {});
      };
    };
    let disconnect = connect();
    const close = () => disconnect();
    window.addEventListener("pagehide", close);
    const restore = (event: PageTransitionEvent) => {
      if (event.persisted) disconnect = connect();
    };
    window.addEventListener("pageshow", restore);
    return () => {
      disconnect();
      window.removeEventListener("pagehide", close);
      window.removeEventListener("pageshow", restore);
    };
  }, []);
}
