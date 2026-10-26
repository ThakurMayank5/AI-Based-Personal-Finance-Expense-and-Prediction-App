import { useState } from 'react';
import { ActivityIndicator, Alert, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { useAuth } from '@/context/auth-context';
import { api } from '@/lib/api';

export function AuthScreen() {
  const { login, register, busy } = useAuth();
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');

  async function submit() {

    console.log('Signing In')

    try {
      // Temporary connectivity probe requested for sign-in debugging. Remove
      // this block once the server connection has been confirmed.
      try {
        const ping = await api.ping();
        console.log('Finance API ping:', ping.message);
      } catch (pingError) {
        console.warn('Finance API ping failed:', pingError);
      }
      console.log(email, password);
      if (creating) await register(name, email, password);
      else await login(email, password);


    } catch (error) {
      Alert.alert('Unable to continue', error instanceof Error ? error.message : 'Please try again.');
    }
  }

  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.content}>
        <View style={styles.heading}>
          <View><Text style={styles.eyebrow}>Finance</Text><Text style={styles.title}>{creating ? 'Create account' : 'Sign in'}</Text></View>
          <Text style={styles.subtext}>{creating ? 'Start tracking your expenses in one place.' : 'Sign in to view your money clearly.'}</Text>
        </View>
        <View style={styles.form}>
          {creating && <TextInput value={name} onChangeText={setName} placeholder="Name" placeholderTextColor="#7A879A" style={styles.input} autoCapitalize="words" />}
          <TextInput value={email} onChangeText={setEmail} placeholder="Email address" placeholderTextColor="#7A879A" style={styles.input} autoCapitalize="none" autoCorrect={false} keyboardType="email-address" />
          <TextInput value={password} onChangeText={setPassword} placeholder="Password (8+ characters)" placeholderTextColor="#7A879A" style={styles.input} secureTextEntry />
          <Pressable disabled={busy} onPress={submit} style={({ pressed }) => [styles.primary, (pressed || busy) && styles.dimmed]}>
            {busy ? <ActivityIndicator color="#FFFFFF" /> : <Text style={styles.primaryText}>{creating ? 'Create account' : 'Sign in'}</Text>}
          </Pressable>
        </View>
        <Pressable onPress={() => setCreating((value) => !value)} disabled={busy} style={styles.switchButton}>
          <Text style={styles.switchText}>{creating ? 'Already have an account? Sign in' : 'New here? Create an account'}</Text>
        </Pressable>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#FFFFFF' }, content: { flex: 1, justifyContent: 'center', padding: 24, maxWidth: 520, width: '100%', alignSelf: 'center' },
  heading: { gap: 8, marginBottom: 28 }, eyebrow: { fontSize: 14, color: '#555555', fontWeight: '600' }, title: { color: '#111111', fontSize: 30, fontWeight: '700', marginTop: 2 }, subtext: { color: '#666666', fontSize: 16, lineHeight: 22 },
  form: { gap: 12 }, input: { backgroundColor: '#FFFFFF', borderWidth: 1, borderColor: '#CFCFCF', borderRadius: 4, paddingHorizontal: 14, height: 52, color: '#111111', fontSize: 16 },
  primary: { height: 52, borderRadius: 4, backgroundColor: '#222222', justifyContent: 'center', alignItems: 'center', marginTop: 4 }, primaryText: { color: '#FFFFFF', fontSize: 16, fontWeight: '600' }, dimmed: { opacity: 0.65 },
  switchButton: { alignSelf: 'center', padding: 20 }, switchText: { color: '#333333', fontWeight: '600' },
});
