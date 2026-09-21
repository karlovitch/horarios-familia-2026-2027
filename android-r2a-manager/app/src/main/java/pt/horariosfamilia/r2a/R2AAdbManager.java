package pt.horariosfamilia.r2a;

import android.content.Context;
import android.os.Build;
import android.sun.misc.BASE64Encoder;
import android.sun.security.provider.X509Factory;
import android.sun.security.x509.AlgorithmId;
import android.sun.security.x509.CertificateAlgorithmId;
import android.sun.security.x509.CertificateExtensions;
import android.sun.security.x509.CertificateIssuerName;
import android.sun.security.x509.CertificateSerialNumber;
import android.sun.security.x509.CertificateSubjectName;
import android.sun.security.x509.CertificateValidity;
import android.sun.security.x509.CertificateVersion;
import android.sun.security.x509.CertificateX509Key;
import android.sun.security.x509.KeyIdentifier;
import android.sun.security.x509.PrivateKeyUsageExtension;
import android.sun.security.x509.SubjectKeyIdentifierExtension;
import android.sun.security.x509.X500Name;
import android.sun.security.x509.X509CertImpl;
import android.sun.security.x509.X509CertInfo;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.security.KeyFactory;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.NoSuchAlgorithmException;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.SecureRandom;
import java.security.cert.Certificate;
import java.security.cert.CertificateEncodingException;
import java.security.cert.CertificateException;
import java.security.cert.CertificateFactory;
import java.security.spec.EncodedKeySpec;
import java.security.spec.InvalidKeySpecException;
import java.security.spec.PKCS8EncodedKeySpec;
import java.util.Date;
import java.util.Random;

import io.github.muntashirakon.adb.AbsAdbConnectionManager;

public class R2AAdbManager extends AbsAdbConnectionManager {
    private static R2AAdbManager INSTANCE;

    public static synchronized R2AAdbManager getInstance(@NonNull Context context) throws Exception {
        if (INSTANCE == null) {
            INSTANCE = new R2AAdbManager(context.getApplicationContext());
        }
        return INSTANCE;
    }

    public static synchronized R2AAdbManager recreate(@NonNull Context context) throws Exception {
        if (INSTANCE != null) {
            try {
                INSTANCE.disconnect();
            } catch (Throwable ignored) {
            }
        }
        INSTANCE = new R2AAdbManager(context.getApplicationContext());
        return INSTANCE;
    }

    private PrivateKey privateKey;
    private Certificate certificate;

    private R2AAdbManager(@NonNull Context context) throws Exception {
        setApi(Build.VERSION.SDK_INT);
        privateKey = readPrivateKeyFromFile(context);
        certificate = readCertificateFromFile(context);
        if (privateKey == null || certificate == null) {
            generateIdentity(context);
        }
    }

    private void generateIdentity(@NonNull Context context) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048, SecureRandom.getInstance("SHA1PRNG"));
        KeyPair pair = generator.generateKeyPair();
        PublicKey publicKey = pair.getPublic();
        privateKey = pair.getPrivate();

        String subject = "CN=R2A Diagnostico";
        String algorithmName = "SHA256withRSA";
        long now = System.currentTimeMillis();
        long expiryDate = now + (3650L * 24L * 60L * 60L * 1000L);

        CertificateExtensions extensions = new CertificateExtensions();
        extensions.set("SubjectKeyIdentifier",
                new SubjectKeyIdentifierExtension(new KeyIdentifier(publicKey).getIdentifier()));

        X500Name x500Name = new X500Name(subject);
        Date notBefore = new Date(now - 60_000L);
        Date notAfter = new Date(expiryDate);
        extensions.set("PrivateKeyUsage", new PrivateKeyUsageExtension(notBefore, notAfter));

        CertificateValidity validity = new CertificateValidity(notBefore, notAfter);
        X509CertInfo info = new X509CertInfo();
        info.set("version", new CertificateVersion(2));
        info.set("serialNumber", new CertificateSerialNumber(new Random().nextInt() & Integer.MAX_VALUE));
        info.set("algorithmID", new CertificateAlgorithmId(AlgorithmId.get(algorithmName)));
        info.set("subject", new CertificateSubjectName(x500Name));
        info.set("key", new CertificateX509Key(publicKey));
        info.set("validity", validity);
        info.set("issuer", new CertificateIssuerName(x500Name));
        info.set("extensions", extensions);

        X509CertImpl cert = new X509CertImpl(info);
        cert.sign(privateKey, algorithmName);
        certificate = cert;

        writePrivateKeyToFile(context, privateKey);
        writeCertificateToFile(context, certificate);
    }

    @NonNull
    @Override
    protected PrivateKey getPrivateKey() {
        return privateKey;
    }

    @NonNull
    @Override
    protected Certificate getCertificate() {
        return certificate;
    }

    @NonNull
    @Override
    protected String getDeviceName() {
        return "R2A-Diagnostico";
    }

    @Nullable
    private static Certificate readCertificateFromFile(@NonNull Context context)
            throws IOException, CertificateException {
        File certFile = new File(context.getFilesDir(), "r2a-cert.pem");
        if (!certFile.exists()) return null;
        try (InputStream cert = new FileInputStream(certFile)) {
            return CertificateFactory.getInstance("X.509").generateCertificate(cert);
        }
    }

    private static void writeCertificateToFile(@NonNull Context context, @NonNull Certificate certificate)
            throws CertificateEncodingException, IOException {
        File certFile = new File(context.getFilesDir(), "r2a-cert.pem");
        BASE64Encoder encoder = new BASE64Encoder();
        try (OutputStream os = new FileOutputStream(certFile)) {
            os.write(X509Factory.BEGIN_CERT.getBytes(StandardCharsets.UTF_8));
            os.write('\n');
            encoder.encode(certificate.getEncoded(), os);
            os.write('\n');
            os.write(X509Factory.END_CERT.getBytes(StandardCharsets.UTF_8));
        }
    }

    @Nullable
    private static PrivateKey readPrivateKeyFromFile(@NonNull Context context)
            throws IOException, NoSuchAlgorithmException, InvalidKeySpecException {
        File keyFile = new File(context.getFilesDir(), "r2a-private.key");
        if (!keyFile.exists()) return null;
        byte[] bytes = new byte[(int) keyFile.length()];
        try (InputStream is = new FileInputStream(keyFile)) {
            int offset = 0;
            while (offset < bytes.length) {
                int count = is.read(bytes, offset, bytes.length - offset);
                if (count < 0) break;
                offset += count;
            }
        }
        KeyFactory factory = KeyFactory.getInstance("RSA");
        EncodedKeySpec spec = new PKCS8EncodedKeySpec(bytes);
        return factory.generatePrivate(spec);
    }

    private static void writePrivateKeyToFile(@NonNull Context context, @NonNull PrivateKey privateKey)
            throws IOException {
        File keyFile = new File(context.getFilesDir(), "r2a-private.key");
        try (OutputStream os = new FileOutputStream(keyFile)) {
            os.write(privateKey.getEncoded());
        }
    }
}
