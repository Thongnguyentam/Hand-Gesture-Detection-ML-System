
```
helm-chart/
├── Chart.yaml              
├── values.yaml             ✅ configuration (image name, ports, etc.)
├── templates/
│   ├── deployment.yaml     # your K8s deployment spec
│   ├── service.yaml        ✅ your K8s service spec
│   └── ingress.yaml        (optional)
```

- `ingress.yaml`: defines a Kubernetes Ingress resource, which exposes your app to the outside world
    - Deploys one external LoadBalancer for the ingress controller.
    - All requests come through this one point.
    - Uses Ingress resources to route traffic to different services by domain or path.
- `templates/deployment.yaml`: “I want n copies of this app, using this Docker image, always running.” 
    - The Deployment controller's job is to ensure that a specified number of identical pods (replicas) are always running and healthy. If a pod crashes, the Deployment's controller will automatically create a new one to replace it. It is the true "manager" of the pods' lifecycle.
    - The `spec.template` section in your deployment.yaml is a blueprint. Every single pod that the Deployment creates will be an exact clone based on that blueprint—same container image, same ports, same environment variables, etc.

- `templates/service.yaml`: Exposes your pods to the network (inside the cluster, or publicly)
    - `type: LoadBalancer`: helps expose the pods and your service directly to the internet with a public IP 
    - `type: ClusterIP`
    - Pods are ephemeral; they can be created and destroyed, and their internal IP addresses will change. The Service provides a single, stable IP address and DNS name that other parts of your cluster can use to talk to those pods. It uses a selector to continuously scan for pods that have a matching label.

## Anology 

- `The Pods:` These are the individual chefs working inside the trucks. They do the actual cooking.
- `The Deployment:` This is the operations manager. They are responsible for hiring the chefs, making sure they all have the same uniform and training (spec.template), and ensuring there are always three chefs working (replicas: 3). If a chef gets sick and goes home, the manager immediately sends in an identical replacement.
- `The Service:` This is the single, permanent phone number customers can call to place an order (ClusterIP and DNS name). This phone number never changes, even if the individual chefs on duty do. The service automatically routes the call to a chef who is ready to take an order.
- `The Ingress:` This is the main website or menu board out on the street. It lists the different items you can order (e.g., /tacos, /burritos). When a customer places an order from the website (http request), the ingress directs that specific order to the correct phone number (Service).

```shell
helm lint . # checks for syntax errors and missing values.
```

Creates a local Kubernetes cluster (usually a single-node cluster):
```shell
minikube start
```

Install helm chart:
```shell
helm install hand-gesture ./asl --namespace model-serving --create-namespace
```

Upgrade helm chart:
```shell
helm upgrade hand-gesture ./asl --namespace model-serving
```

Check if there are 2 pods up and the service:
```shell
kubectl get pods -n model-serving
kubectl get svc -n model-serving
```


`nginx.ingress.kubernetes.io/ssl-redirect: "false"`
What it does: It controls whether the NGINX Ingress should automatically redirect incoming HTTP traffic (on port 80) to HTTPS (on port 443).
- "false" (Our current setting): By setting this to "false", we are telling NGINX: "Do not force an HTTPS redirect." If a user makes a request to http://your-domain.com, they will be served content over HTTP. This is common and acceptable for development, testing, or when you haven't set up TLS/SSL certificates yet.

- "true" (The production standard): In a production environment, you would almost always set this to "true". This enhances security by ensuring that all communication between the client and your application is encrypted. If a user tried to access your site via HTTP, NGINX would automatically send them a 301 redirect to the https:// version of the URL. To use this, you would also need to have a TLS certificate configured for your Ingress.


### Step 1: The Secret is Defined
In `helm-charts/asl/templates/secrets.yaml`, you define a Secret resource. Helm will process this template and create a secret in your cluster named something like `hand-gesture-secrets`.
This secret contains key-value pairs, like:
MONGODB_CONNECTION_URL: bW9uZ29kYitzcnY6Ly9... (Base64 encoded)
JWT_SECRET: ZXlKaGJHY2lPaUp... (Base64 encoded)

### Step 2: The Deployment Consumes the Secret

```yaml
// ... inside the container definition
          envFrom:
            - secretRef:
                name: {{ .Release.Name }}-secrets
// ...
```
This block tells Kubernetes how to set up environment variables for your application's container. Let's break it down:
- `envFrom`: This is a list of sources from which to populate environment variables. It says, "Instead of defining variables one-by-one, get them in bulk from somewhere else."
- `secretRef`: This specifies that the source is a Kubernetes Secret. (Ref is short for "Reference").
- `name: {{ .Release.Name }}-secrets:` This is the most important part. It tells the pod exactly which secret to use. The name `{{ .Release.Name }}-secrets` is dynamically generated by Helm to match the name of the secret created in Step 1.
- *The Result:* When Kubernetes creates a pod for this deployment, it performs these actions:
    - It finds the Secret named hand-gesture-secrets.
    - It looks at all the key-value pairs inside the secret's data field.
    - For each key, it creates an environment variable inside your container with the same name as the key.
    - It automatically Base64-decodes the value and assigns the plain-text result to that environment variable.

## Ingress → Service → Pod (Container)

### 1. The Container Port (in `deployment.yaml`)
This is the port your application is actually listening on inside the container.
File: `helm-charts/asl/templates/deployment.yaml`

```yaml
//...
      containers:
        - name: {{ .Release.Name }}
//...
          ports:
            - containerPort: {{ .Values.service.port }}
//...
```
- `containerPort: {{ .Values.service.port }}`: You are telling Kubernetes that your application process inside this container is bound to a specific port (which you've defined in values.yaml, e.g., 30000). This is the final destination of the traffic.

### 2. The Service Ports (in `service.yaml`)
The Service acts as a stable internal load balancer for your pods. It has two important port definitions:
File: `helm-charts/asl/templates/service.yaml`

```yaml
//...
spec:
  ports:
    - port: {{ .Values.service.port }}
      protocol: TCP
      targetPort: {{ .Values.service.port }}
//...
```

- `targetPort`: This tells the Service, "When you receive traffic, forward it to this port on the Pod." This port MUST match the containerPort from your `deployment.yaml`. In your case, both use `{{ .Values.service.port }}`, which is correct.
- `port`: This is the port that the Service itself exposes to the rest of the cluster. Other services or the Ingress controller will send traffic to this port.
You have set both port and targetPort to the same value (`{{ .Values.service.port }}`). This is a very common and straightforward setup. It means the Service listens on port 30000 and forwards to the pod on port 30000.

### 3. The Ingress Backend Port (in `ingress.yaml`)
The Ingress directs external traffic to your Service. It needs to know which port on the Service to send the traffic to.
File: `helm-charts/asl/templates/ingress.yaml`
```yaml
//...
            backend:
              service:
                name: {{ .Release.Name }}
                port:
                  number: {{ .Values.service.port }}
//...
```
port.number: This tells the Ingress controller, "Send the traffic to the port number `{{ .Values.service.port }}` on the service named `{{ .Release.Name }}`." This port MUST match the port from your service.yaml. Again, you've correctly used the same value here.



First, your service should not be a LoadBalancer. The Ingress will be the single public entry point with a load balancer. Your internal services should be reachable only within the cluster.


When your application pod starts, Kubernetes automatically decodes this Base64 value and presents the original, plain-text "my-secret-password" to your application as an environment variable. This whole process ensures that secrets are handled securely and in the format Kubernetes expects.

