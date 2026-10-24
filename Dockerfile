# syntax=docker/dockerfile:1

# ---- 构建层:JDK 21 + Maven,产物为可执行 jar ----
FROM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /build
COPY pom.xml .
# 先拉依赖再拷源码,利用层缓存加速重复构建
RUN --mount=type=cache,target=/root/.m2 mvn -q dependency:go-offline
COPY src ./src
RUN --mount=type=cache,target=/root/.m2 mvn -q package -DskipTests

# ---- 运行层:仅 JRE,非 root 用户 ----
FROM eclipse-temurin:21-jre
WORKDIR /app
RUN groupadd -r chatbi && useradd -r -g chatbi chatbi
COPY --from=build /build/target/*.jar app.jar
USER chatbi
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "app.jar"]
