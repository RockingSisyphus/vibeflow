// Observe actual Program builds without changing analysis or cache decisions.
import {register} from 'node:module';
register(new URL('./program_loader.mjs',import.meta.url));
