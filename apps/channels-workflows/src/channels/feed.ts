import { defineChannel } from "tako.sh";

type FeedMessages = {
  tick: { seq: number; at: number };
};

export default defineChannel("feed", {
  replayWindowMs: 60_000,
}).$messageTypes<FeedMessages>();
