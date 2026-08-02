import { runWorkflowAsync } from "@vibeflow/workflow";

const input = document.querySelector<HTMLInputElement>("#name");
const button = document.querySelector<HTMLButtonElement>("#run");
const output = document.querySelector<HTMLOutputElement>("#output");

if (!input || !button || !output) {
  throw new Error("example page is missing required elements");
}

button.addEventListener("click", async () => {
  const result = await runWorkflowAsync(
    { name: input.value },
    {
      capabilities: {
        "example.clock": {
          now: async () => Date.now(),
        },
      },
    },
  );
  output.value = result.greeting;
});
