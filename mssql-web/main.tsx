import React from 'react';
import {createRoot} from 'react-dom/client';
import AuthRoot from './auth';
import '../app/globals.css';
import '../app/club.css';
createRoot(document.getElementById('root')!).render(<AuthRoot/>);
