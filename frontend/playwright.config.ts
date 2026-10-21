import {defineConfig} from '@playwright/test'
export default defineConfig({testDir:'./e2e',workers:1,timeout:30000,use:{baseURL:process.env.SWE_BROWSER_URL||'http://host.docker.internal:18090',headless:true,screenshot:'only-on-failure'},reporter:[['list']],outputDir:'test-results'})
