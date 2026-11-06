# Dashboard development

I built a filterable production view because I wanted to find slow runs without reading every row. Follow the clean-checkout steps in the [project README](../README.md) first.

From the repository root, `npm run dev` starts the Angular development server on port 4200 and the API on port 3000. Requests to `/api` are forwarded through `proxy.conf.json`. `npm test --workspace web -- --watch=false` runs the dashboard tests; `npm run build --workspace web` builds the browser files.
