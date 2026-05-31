import { defineWorkflow } from "tako.sh";

type Payload = {
  seq: number;
  at: number;
};

export default defineWorkflow<Payload>("noop", {
  retries: 0,
  concurrency: 100,
  handler: async (payload, ctx) => {
    await ctx.run("ack", () => payload.seq);
  },
});
